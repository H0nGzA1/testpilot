# Session Persistence & Multi-Account / Multi-Env Auth — Design Spec

Status: **LOCKED** (all decisions confirmed 2026-08-14 via grilling)
Author: drafted 2026-08-14

## Decisions (locked)

- **D1 — mechanism**: full session bundle (cookies + localStorage + sessionStorage) + pre-load injection via CDP. ✅
- **D2 — expiry**: **no TTL heuristic.** Reuse the bundle indefinitely; refresh **only reactively** when auth actually fails (401 / login redirect). Drop `expires_at` as a proactive knob. ✅
- **D3 — detection**: **A + B** — CDP network watch for 401/403 on app API calls (primary) + login-page/redirect detection (backstop). Self-heal = invalidate bundle → single-flight re-login + re-capture → **retry the case once**. ✅
- **D4 — multi-tab**: **deferred.** Single-tab flows only; 401/login detection scoped to the **main tab** so a stray new tab (empty sessionStorage) can't trigger a spurious refresh. Add per-target seeding later if a real case needs multiple tabs. ✅

## Goal

Three asks, one design:
1. **多账号** — a case runs as a chosen account (e.g. requester / approver).
2. **多环境** — the same case can run against dev / test / prod, each with its own base URL and accounts.
3. **不要每次都登录 / 保存认证信息** — capture an account's login **once**, reuse it across every case/run, auto-refresh when it expires. No per-case login.

(1) and (2) already exist (Credential.role / environment_id, account leasing, Environment.base_url). This spec is mostly about (3), which is genuinely unsolved today, plus folding all three into one coherent auth model.

## Why (3) isn't solved today

- The **default** account captures a `storage_state` (cookies + localStorage) and injects it → reuse works for cookie/localStorage apps.
- But two problems:
  - **Injecting `storage_state` detaches browser-use's CDP target** → every screenshot goes blank (documented in `executor.py`). So we only inject it when there's no login account.
  - **`storage_state` does not include `sessionStorage`.** The app under test keeps its auth token in `sessionStorage`, so a restored `storage_state` is *not* logged in → the agent must re-login. That's why role/password accounts do **prompt-login on every case** — slow (login burns the 25-30s/step budget, cases often time out before finishing).

## Chosen mechanism — full session bundle + pre-load injection

> Open decision D1 (recommended). Alternative considered: keep a warm logged-in browser alive per account — fastest but holds one browser per account continuously, fighting the global 16-browser budget. Rejected as default.

**Session bundle** = everything an origin needs to be "logged in":

```json
{ "cookies": [...], "localStorage": {origin: {k: v}}, "sessionStorage": {origin: {k: v}} }
```

(IndexedDB-based auth is out of scope — rare; falls back to prompt-login.)

**Capture** (once, after a successful login via the stored password account):
- cookies → CDP `Network.getAllCookies` / `Storage.getCookies`
- localStorage + sessionStorage → `Runtime.evaluate` reading `window.localStorage` / `window.sessionStorage` per origin (we already reach private CDP via `browser._cdp_*`).

**Restore** (per case, before the app's JS runs):
- cookies → CDP `Network.setCookies` before navigation.
- localStorage + sessionStorage → CDP `Page.addScriptToEvaluateOnNewDocument` with a small seeding script that runs at *document-start* (before app scripts), populating both stores from the bundle.

This does the two things `storage_state` can't: **restores `sessionStorage`** (so the app is logged in), and **keeps browser-use's CDP target attached** (we inject via our own CDP calls instead of the `storage_state=` launch path → no blank-screenshot detach).

## Data model

Generalize a Credential to carry BOTH the refresh material and the reusable session:

| field | role |
|-------|------|
| `username` / `password` (encrypted) | how to (re)login for refresh |
| `session_bundle` (encrypted JSON) | the reusable captured session (NEW; replaces the storage_state-only `secret` for password accounts) |
| `role`, `environment_id` | selection (existing) |
| `healthy`, `last_error`, `last_checked_at` | health (existing) |

No TTL/`expires_at` (D2): the bundle is reused until auth actually fails, then re-captured.

So every account = *credentials to refresh* + *a cached session to reuse*. Multi-account = multiple Credentials; multi-env = env-scoped Credentials; the bundle is per-Credential, so per-account and per-env sessions are naturally separate.

## Run-time flow (per case)

1. Resolve the Credential for `(case.role, run.environment)` — existing `_role_candidates` + Redis leasing.
2. **Has a bundle?** → restore it (cookies + storage seed) → agent starts logged in, **skip login**.
3. **No bundle** → prompt-login once with the password, then **capture a fresh bundle + persist it** (next case reuses it).
4. **Auth fails** (D3: 401/403 on an app API, or redirect to login on the main tab) → invalidate the bundle, single-flight re-login + re-capture, **retry the case once**.

### Single-flight refresh (important)

With 16 parallel cases, a stale/absent bundle must NOT trigger 16 simultaneous logins. Guard refresh with a **per-credential lock** (Redis SET NX, same infra as account leasing): the first case logs in + captures; the rest wait briefly and reuse the fresh bundle.

## Refresh — purely reactive (D2)

No TTL guessing (enterprise sessions are usually *idle* timeouts anyway, which a
capture-time TTL can't model). The bundle is reused until auth actually fails:

- **Detect** (D3): CDP `Network.responseReceived` sees 401/403 on an app API call (primary), or the main tab is redirected to a login page (backstop).
- **Heal**: invalidate the bundle → single-flight (Redis lock) re-login with the stored password → re-capture → **retry the case once**. Second failure = real failure.
- Detection is scoped to the **main tab** (D4) so a stray new tab can't trigger a spurious refresh.

## Security

- `session_bundle` holds live tokens/cookies → **encrypted at rest** (Fernet, like `secret`); never sent to the client (`_cred` already omits secrets); redacted in logs.

## Risks / edge cases

- `sessionStorage` is per-tab; `addScriptToEvaluateOnNewDocument` seeds each new document → fine for single-tab flows; multi-tab needs per-target seeding (defer).
- Tokens bound to device/IP fingerprint may be rejected on restore → falls back to prompt-login + recapture (self-heals, just slower that once).
- Rotating CSRF/nonce in storage → capture whole-origin; server-side session cookies usually cover it.

## Phasing

- **P1** — full-bundle capture+restore for the **default** account (replace the storage_state path). Verify on the app under test: reuse works (no re-login) **and** screenshots aren't blank.
- **P2** — extend to **role / env** accounts (every account captures + reuses); add the single-flight refresh lock.
- **P3** — reactive detect (401/403 + login redirect) → invalidate → re-capture → retry-once.

Multi-tab per-target seeding is out of scope until a real case needs it (D4).
