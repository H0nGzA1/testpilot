"""Per-case executor: drive a real browser via browser-use (Playwright/CDP under the
hood), record video + trace, then judge pass/fail.

browser-use is imported lazily so `app.engine` can be imported (and unit-tested)
without the heavy browser stack installed.
"""

from __future__ import annotations

import asyncio
import base64
import glob
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.judge import judge

# a page whose URL looks like a login/auth screen — used to detect a dead restored
# session (P3) and a capture that didn't actually log in (P2.5). Apps typically redirect an
# unauthenticated visit to /login, so the URL trail is a reliable signal.
_LOGIN_URL_RE = re.compile(r"login|sign-?in|/auth\b", re.I)

# Every element index in a step comes from the snapshot taken BEFORE the step's actions.
# A dropdown/popover's options don't exist in that snapshot, so an index planned for them
# in the same step points at unrelated page content — clicking it closes the popup without
# selecting, and the next snapshot shows it closed again. That loop cost a VRS run 20
# identical steps against a Base UI multi-select.
_POPUP_RULE = """
Opening a dropdown, select, combobox, date picker, autocomplete, menu or any other popover
MUST be the LAST action of the step. Its options do not exist yet in the page state you are
looking at, so any index you pick for them in the same step is a guess at unrelated content.
End the step after the opening click, read the next page state, then click the real option.
If a popup looks open but you cannot find its options in the page state, do NOT click a
nearby index — say so and try keyboard selection (type to filter, arrow keys, Enter) instead.
""".strip()

# The app under test is on a private network. When its URL failed to load the agent kept
# "looking for the site" on Google/Baidu, which cannot reach it either — that burned whole
# runs (VRS runs 28/29 timed out searching, run 39 searched for a localhost URL).
_SCOPE_RULE = """
You are testing ONE web application, reachable only at the URL you were started on. Never
navigate to a search engine, and never look for the application on the public internet: it
is on a private network and is not indexed anywhere. If the page fails to load
(ERR_CONNECTION_REFUSED, DNS error, timeout), do not go looking for an alternative address
— report the exact URL and the exact browser error and stop. That is the useful result.
""".strip()


def _last_url_is_login(history) -> bool:
    """True if the agent's final page looked like a login screen (read from history —
    robust, unlike probing the live browser after the run)."""
    urls = _safe(lambda: history.urls()) or []
    last = next((u for u in reversed(urls) if u), None)
    return bool(last and _LOGIN_URL_RE.search(last))


@dataclass(frozen=True)
class CaseSpec:
    case_id: int
    prompt: str
    expected: str = ""
    start_url: str | None = None
    login_state: str | None = None  # storage_state JSON string, or None
    login_username: str | None = None  # robot account for per-run prompt-login
    login_password: str | None = None
    timeout_s: int = 0  # 0 => fall back to settings.case_timeout_s
    max_steps: int = 0  # 0 => fall back to settings.case_max_steps
    # RunResult id — the artifact folder. Keying artifacts by case_id made every re-run of
    # a case overwrite the previous run's screenshots/video, so old reports silently showed
    # the newest run's frames. 0 falls back to the case id (nothing constructs a spec
    # without a result row today; the fallback just keeps paths well-formed).
    result_id: int = 0


@dataclass
class ResultSpec:
    case_id: int
    status: str = "error"  # passed | failed | error
    video_url: str | None = None
    trace_url: str | None = None
    steps: list = field(default_factory=list)
    diagnostics: list = field(
        default_factory=list
    )  # per-step [{i,action,thought,result,error,screenshot}]
    judge_reason: str | None = None
    final_answer: str | None = None
    latency_ms: int = 0
    error: str | None = None
    auth_failed: bool = False  # restored session was dead (ended on a login page) → self-heal
    timed_out: bool = False  # hit the wall-clock cap → a re-attempt cannot change the outcome


def _read_b64(path: str | None) -> str | None:
    """A local file as base64, or None. Used to hand the judge the final frame."""
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode()
    except OSError:
        return None


def _newest(pattern: str) -> str | None:
    hits = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return hits[0] if hits else None


def _build_diagnostics(history) -> list[dict]:
    """Per-step timeline from a browser-use AgentHistoryList: what the model thought,
    the action it took, the result/error, and the local screenshot path (uploaded later).
    Reads history.history directly so it works even when a run is cut short by timeout."""
    items = list(getattr(history, "history", None) or [])
    paths = _safe(lambda: history.screenshot_paths()) or []
    steps: list[dict] = []
    for i, h in enumerate(items):
        mo = getattr(h, "model_output", None)
        thought = ""
        actions: list[str] = []
        if mo is not None:
            thought = (
                getattr(mo, "thinking", None) or getattr(mo, "next_goal", None) or ""
            ).strip()
            for a in getattr(mo, "action", None) or []:
                dumped = a.model_dump(exclude_none=True) if hasattr(a, "model_dump") else {}
                actions.extend(dumped.keys())
        results = list(getattr(h, "result", None) or [])
        error = next((r.error for r in results if getattr(r, "error", None)), None)
        content = next(
            (r.extracted_content for r in results if getattr(r, "extracted_content", None)), None
        )
        steps.append(
            {
                "i": i + 1,
                "action": ", ".join(actions) or "—",
                "thought": thought,
                "result": (content or "")[:600],
                "error": (error or "")[:600],
                "screenshot": paths[i] if i < len(paths) else None,  # local path; uploaded below
            }
        )
    return steps


def build_task(spec: CaseSpec, report_language: str) -> str:
    """The instruction handed to the agent. Split out so the login-fallback rule below is
    testable without a browser."""
    parts = []
    if spec.start_url:
        parts.append(f"First go to {spec.start_url}.")
    # ALWAYS hand over the credentials, restored session or not. An expired session lands
    # the agent on the login page, and withholding them there left it either giving up
    # ("缺少登录凭据") or inventing a password and tripping the app's 「请求过于频繁」
    # rate limit for every other case in the run.
    if spec.login_username:
        parts.append(
            f"If a login page is shown, log in with username '{spec.login_username}' and "
            f"password '{spec.login_password}', reading and answering any simple captcha; "
            "if a first-login password change is forced, set a new valid password and continue. "
            "Use exactly this username and password — never invent credentials, and if login "
            "is refused (rate limited, wrong password) stop and report it instead of retrying."
        )
    parts.append(f"Then perform this task: {spec.prompt}")
    parts.append(
        f"Write all of your thinking, reasoning, evaluation and the final answer in {report_language}."
    )
    return " ".join(parts)


async def execute_case(spec: CaseSpec, on_step=None, should_abort=None) -> ResultSpec:
    """Run one NL test case in a fresh browser. Never raises — errors are captured.

    on_step(live_steps): optional async callback invoked after every browser-use step
    with the running list of {i, action, thought, screenshot} — powers the live view.
    should_abort(): optional async predicate checked every step; True stops the agent
    (that is how cancelling a run reaches a case that is already driving a browser)."""
    from app.storage import upload

    s = get_settings()
    res = ResultSpec(case_id=spec.case_id)
    t0 = time.monotonic()
    art = f"runs/{spec.result_id or spec.case_id}"  # this attempt's artifact folder
    final_shot: str | None = None

    with tempfile.TemporaryDirectory(prefix=f"tp_case_{spec.case_id}_") as workdir:
        video_dir = os.path.join(workdir, "video")
        trace_dir = os.path.join(workdir, "trace")
        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(trace_dir, exist_ok=True)

        browser = None
        agent = None
        live_steps: list[dict] = []
        timeout_s = spec.timeout_s or s.case_timeout_s
        max_steps = spec.max_steps or s.case_max_steps
        try:
            from browser_use import Agent, Browser

            from app.llm import browser_use_llm

            # ponytail: record_video_dir / traces_dir are the Playwright-context recording
            # knobs. Their exact names on Browser/BrowserProfile drift across browser-use
            # releases — verify against the pinned version at first install and adjust here only.
            browser = Browser(
                headless=True,
                # never fetch the default uBlock/cookie extensions — that download is a
                # blocking call with no internet in the container (it froze the API).
                enable_default_extensions=False,
                record_video_dir=video_dir,
                traces_dir=trace_dir,
            )
            # Prefer restoring a captured session bundle so the agent starts logged in
            # (cookies + storage seeded at document-start via CDP — not the storage_state=
            # launch path, which drops sessionStorage and detaches CDP → blank screenshots).
            if spec.login_state:
                await _safe_async(lambda: _restore_session(browser, spec.login_state))
            task = build_task(spec, s.report_language)

            async def _step_cb(browser_state, model_output, step_no):
                # stream each step live: model thought + action + current screenshot.
                # browser-use keeps screenshots in-memory (not on disk), so grab one via
                # CDP here rather than relying on browser_state.screenshot / screenshot_paths.
                try:
                    thought = (
                        getattr(model_output, "thinking", None)
                        or getattr(model_output, "next_goal", None)
                        or ""
                    ).strip()
                    actions: list[str] = []
                    for a in getattr(model_output, "action", None) or []:
                        d = a.model_dump(exclude_none=True) if hasattr(a, "model_dump") else {}
                        actions.extend(d.keys())
                    shot_url = None
                    png = await _safe_async(lambda: browser.take_screenshot())
                    if png:
                        p = os.path.join(workdir, f"live-{step_no}.png")
                        data = png if isinstance(png, bytes) else base64.b64decode(png)
                        with open(p, "wb") as f:  # noqa: ASYNC230 — tiny one-shot write
                            f.write(data)
                        shot_url = await _swallow(upload(p, f"{art}/live-{step_no}.png"))
                    live_steps.append(
                        {
                            "i": step_no,
                            "action": ", ".join(actions) or "…",
                            "thought": thought,
                            "result": "",
                            "error": "",
                            "screenshot": shot_url,
                        }
                    )
                    if on_step is not None:
                        await on_step(list(live_steps))
                    if should_abort is not None and await should_abort():
                        res.error = "cancelled"
                        _safe(lambda: agent.stop())
                except Exception:
                    pass

            agent = Agent(
                task=task,
                llm=browser_use_llm(),
                browser=browser,
                register_new_step_callback=_step_cb,
                extend_system_message=f"{_SCOPE_RULE}\n\n{_POPUP_RULE}",
            )
            # nested so a timeout/agent error still lets us harvest agent.history below —
            # wait_for cancels the coroutine and never returns, so we must read agent.history
            # (built up in-place) rather than the run() return value.
            try:
                await asyncio.wait_for(agent.run(max_steps=max_steps), timeout=timeout_s)
            except TimeoutError:
                res.error = f"timeout after {timeout_s}s"
                res.timed_out = True
            except Exception as exc:
                res.error = f"{type(exc).__name__}: {exc}"[:500]
        except Exception as exc:  # browser/agent setup failure
            res.error = res.error or f"{type(exc).__name__}: {exc}"[:500]
        finally:
            if browser is not None:
                # Browser exposes stop()/kill(), not close(); stop() flushes the video file.
                await _safe_async(lambda: browser.stop())

        # harvest diagnostics from the agent's history regardless of outcome (the whole
        # point: a timed-out/failed case still shows what the model thought and did).
        # live_steps already carry per-step screenshots (uploaded in the callback); the
        # history adds each step's result/error, which we merge in by index.
        history = getattr(agent, "history", None) if agent is not None else None
        if history is not None:
            res.final_answer = _safe(lambda: history.final_result()) or ""
            res.steps = _safe(lambda: history.action_names()) or []
            # P3: we restored a session but the agent ended on a login page → session dead.
            # Signal the engine to invalidate + re-capture + retry once.
            if spec.login_state:
                res.auth_failed = _last_url_is_login(history)
            hist = _safe(lambda: _build_diagnostics(history)) or []
            for i, ls in enumerate(live_steps):
                if i < len(hist):
                    ls["result"] = hist[i].get("result", "")
                    ls["error"] = hist[i].get("error", "")
            res.diagnostics = live_steps or hist
            history_path = os.path.join(workdir, "history.json")
            _safe(lambda: history.save_to_file(history_path))
        else:
            res.diagnostics = live_steps

        # A bare "timeout after 600s" reads the same whether the agent was one step from
        # done or stuck on step 3 — and those want opposite fixes (raise the budget vs.
        # fix the case). VRS run 45's seven timeouts had all reached step 21-29 of 30.
        if res.timed_out:
            res.error = (
                f"timeout after {timeout_s}s (reached step {len(res.diagnostics)}/{max_steps})"
            )

        # collect + upload artifacts (best-effort; missing artifacts don't fail the case)
        video = _newest(os.path.join(video_dir, "*"))
        history_file = os.path.join(workdir, "history.json")
        if video:
            res.video_url = await _swallow(upload(video, f"{art}/{os.path.basename(video)}"))
        if os.path.exists(history_file):
            res.trace_url = await _swallow(upload(history_file, f"{art}/history.json"))
        # keep the final frame before the temp dir goes away — the judge runs after this
        # block and it is the only look it gets at the page's actual end state
        final_shot = _read_b64(_newest(os.path.join(workdir, "live-*.png")))

    res.latency_ms = int((time.monotonic() - t0) * 1000)

    if res.error:
        res.status = "error"
    else:
        verdict = await judge(
            spec.expected,
            res.final_answer or "",
            res.steps,
            task=spec.prompt,
            # the browser's own read-backs ("Clicked div role=option …", "Typed …", errors)
            evidence=[
                str(d.get("result") or d.get("error") or "") for d in (res.diagnostics or [])
            ],
            screenshot_b64=final_shot,
        )
        res.status = verdict.status
        res.judge_reason = verdict.reason
    return res


async def capture_session(base_url: str, username: str, password: str) -> str:
    """Log into base_url with a test account server-side and return the captured
    storage_state as a JSON string. The agent reads simple captchas. Raises on failure."""
    from browser_use import Agent, Browser

    from app.llm import browser_use_llm

    s = get_settings()
    # keep_alive so the CDP session survives after agent.run() — otherwise
    # export_storage_state() fails with "Root CDP client not initialized".
    browser = Browser(headless=True, keep_alive=True, enable_default_extensions=False)
    try:
        task = (
            f"Go to {base_url}. Log in with username '{username}' and password '{password}'. "
            "If a simple math or text captcha is shown, read it from the page and enter the answer. "
            "If a first-login password change is forced, set a new valid password and continue. "
            "Finish only once you are on a logged-in page (no longer on the login screen)."
        )
        agent = Agent(task=task, llm=browser_use_llm(), browser=browser)
        await asyncio.wait_for(agent.run(max_steps=s.case_max_steps), timeout=s.case_timeout_s)
        # P2.5: never store a garbage bundle — if login didn't actually complete (agent still
        # on a login page), fail loudly so the caller falls back to prompt-login instead of
        # caching a tokenless session that would make every future case fail.
        if _last_url_is_login(agent.history):
            raise RuntimeError("login did not complete — still on a login page after capture")
        # Full bundle: cookies + per-origin localStorage AND sessionStorage (CDP format).
        # Restored later via CDP (_restore_session), so sessionStorage-based auth
        # survives — unlike the Playwright storage_state format, which drops it.
        state = await browser._cdp_get_storage_state()  # noqa: SLF001 — private API, pinned to browser-use 0.13.x
        return json.dumps(state, ensure_ascii=False)
    finally:
        await _safe_async(lambda: browser.kill())


async def _restore_session(browser, bundle_json: str) -> None:
    """Restore a captured session bundle (from capture_session / _cdp_get_storage_state)
    so the agent starts logged in, WITHOUT the storage_state= launch path:
      - cookies via CDP Storage.setCookies
      - localStorage + sessionStorage seeded at document-start via
        Page.addScriptToEvaluateOnNewDocument, so they exist before the app's own JS runs
        (this is what makes sessionStorage-based auth survive).
    Best-effort: a restore failure just means the agent may see a login page."""
    bundle = json.loads(bundle_json)
    await browser.start()  # idempotent; needed so a CDP target exists before we inject
    # cookies best-effort on their own: a legacy (Playwright-format) bundle may not map
    # cleanly to CDP setCookies, but must NOT block the storage seed below (which is what
    # carries sessionStorage-based auth).
    cookies = bundle.get("cookies") or []
    if cookies:
        await _safe_async(lambda: browser._cdp_set_cookies(cookies))  # noqa: SLF001
    origins: dict[str, dict] = {}
    for o in bundle.get("origins") or []:
        ls = {i["name"]: i["value"] for i in (o.get("localStorage") or [])}
        ss = {i["name"]: i["value"] for i in (o.get("sessionStorage") or [])}
        if ls or ss:
            origins[o["origin"]] = {"localStorage": ls, "sessionStorage": ss}
    if origins:
        # seed each key ONLY if absent. This script runs on *every* new document, so an
        # unconditional setItem re-writes stale values the app just updated — e.g. an app that
        # compares localStorage.DVADMIN3_VERSION against /version-build and reload()s on a
        # mismatch, so re-seeding the old version reloaded the page ~19x/s forever (blank
        # DOM + hung CDP screenshots → the agent sees an empty page). sessionStorage
        # survives same-tab reloads, so auth still restores on the first document.
        seed = (
            "(function(){var D=" + json.dumps(origins, ensure_ascii=False) + ";try{"
            "var d=D[location.origin];if(d){"
            "for(var k in d.localStorage)"
            "if(localStorage.getItem(k)===null)localStorage.setItem(k,d.localStorage[k]);"
            "for(var k in d.sessionStorage)"
            "if(sessionStorage.getItem(k)===null)sessionStorage.setItem(k,d.sessionStorage[k]);"
            "}}catch(e){}})();"
        )
        await browser._cdp_add_init_script(seed)  # noqa: SLF001 — private, pinned to browser-use 0.13.x


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


async def _safe_async(fn):
    try:
        return await fn()
    except Exception:
        return None


async def _swallow(coro):
    try:
        return await coro
    except Exception:
        return None
