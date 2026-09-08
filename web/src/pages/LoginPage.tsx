import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

const FONTS_HREF =
  "https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,200..800;1,6..72,200..600&family=Space+Grotesk:wght@400;500&family=Inter:wght@300;400;500&family=Noto+Serif+SC:wght@300;500;700&display=swap";
const AIFX_SRC = "https://cdn.aidesigner.ai/effects/runtime/v1.js";
const AIFX_KEY = "aifx_pk_4cd018d335884073952bc73ca1b5642e";

/** Load the Google Fonts link + aidesigner liquid-metal runtime once (idempotent). */
function useLoginAssets() {
  useEffect(() => {
    if (!document.getElementById("tp-login-fonts")) {
      const link = document.createElement("link");
      link.id = "tp-login-fonts";
      link.rel = "stylesheet";
      link.href = FONTS_HREF;
      document.head.appendChild(link);
    }
    // The runtime guards on window.AIFX, so re-adding is a no-op; never remove it
    // (its MutationObserver mounts/destroys the effect as the data-aifx node comes and goes).
    if (!document.getElementById("tp-aifx-runtime") && !(window as unknown as { AIFX?: unknown }).AIFX) {
      const s = document.createElement("script");
      s.id = "tp-aifx-runtime";
      s.src = AIFX_SRC;
      s.async = true;
      s.setAttribute("data-aifx-key", AIFX_KEY);
      document.head.appendChild(s);
    }
  }, []);
}

export function LoginPage() {
  const { t } = useTranslation();
  const { login, publicBaseUrl } = useAuth();
  // canonical address to show (configurable via PUBLIC_BASE_URL); fall back to the real host
  const siteHost = (publicBaseUrl || window.location.origin).replace(/^https?:\/\//, "").replace(/\/+$/, "");
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // the same card flips to "forgot password" rather than routing to a second page
  const [forgot, setForgot] = useState(false);
  const [sent, setSent] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useLoginAssets();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate("/");
    } catch {
      setErr(t("Incorrect email or password"));
    } finally {
      setBusy(false);
    }
  };

  const submitForgot = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      await api.forgotPassword(email.trim());
    } catch {
      // the endpoint answers the same either way; a network blip shouldn't hint otherwise
    } finally {
      setBusy(false);
      setSent(true); // deliberately unconditional: never reveal whether the account exists
    }
  };

  // spotlight cursor tracking on the login card
  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const el = cardRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  return (
    <div className="tp-login">
      <style>{CSS}</style>
      <div className="tp-aifx" data-aifx="liquid-metal" aria-hidden="true" />
      <div className="tp-scrim" />
      <div className="tp-stage">
        <div className="tp-topbar">
          <div className="tp-brand">
            <div className="tp-mark">TP</div>
            <span className="tp-wordmark">TestPilot</span>
          </div>
          <div className="tp-topmeta">{siteHost}</div>
        </div>

        <div className="tp-hero">
          <div className="tp-left">
            <div className="tp-eyebrow">
              <span className="tp-dot" />
              01 — Secure Access
            </div>
            <h1 className="tp-h1">
              Testing that<span className="tp-em">runs itself.</span>
            </h1>
            <p className="tp-sub">
              <b>{t("Write test cases in plain language; they run in a real browser and are judged automatically.")}</b>{" "}
              {t("An agentic end-to-end testing platform, built for teams.")}
            </p>
            <div className="tp-compliance">
              <span>
                <i>✓</i> {t("Real browser execution")}
              </span>
              <span>
                <i>✓</i> {t("Multi-account · multi-env · access isolation")}
              </span>
            </div>
          </div>

          <div className="tp-right">
            <div className="tp-card" ref={cardRef} onPointerMove={onMove}>
              <div className="tp-panel-eyebrow">{forgot ? "Reset" : "Sign in"}</div>
              <div className="tp-panel-title">
                {forgot ? t("Reset your password") : t("Sign in to continue")}
              </div>
              {forgot ? (
                sent ? (
                  <>
                    <p className="tp-note">
                      {t("If an account exists for that address, a reset link is on its way. The link is valid for 2 hours.")}
                    </p>
                    <button className="tp-btn" type="button" onClick={() => { setForgot(false); setSent(false); }}>
                      {t("Back to sign in")}
                    </button>
                  </>
                ) : (
                  <form onSubmit={submitForgot}>
                    <label className="tp-label">{t("Email")}</label>
                    <input
                      className="tp-inp"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      autoFocus
                    />
                    <button className="tp-btn" type="submit" disabled={busy || !email.trim()}>
                      {busy ? t("Sending…") : t("Email me a reset link")}
                    </button>
                    <button className="tp-link" type="button" onClick={() => setForgot(false)}>
                      {t("Back to sign in")}
                    </button>
                  </form>
                )
              ) : (
                <form onSubmit={submit}>
                  <label className="tp-label">{t("Email")}</label>
                  <input
                    className="tp-inp"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoFocus
                  />
                  <div className="tp-gap" />
                  <label className="tp-label">{t("Password")}</label>
                  <input
                    className="tp-inp"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                  />
                  {err && <div className="tp-err">{err}</div>}
                  <button className="tp-btn" type="submit" disabled={busy}>
                    {busy ? t("Signing in…") : t("Sign in")}
                  </button>
                  <button className="tp-link" type="button" onClick={() => { setErr(""); setForgot(true); }}>
                    {t("Forgot your password?")}
                  </button>
                </form>
              )}
              <p className="tp-foot">
                {t("Need access? Contact a system administrator to provision your account.")}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const CSS = `
.tp-login{--ink:#EBEBEB;--emerald:#10b981;--line:rgba(255,255,255,.1);--ease:cubic-bezier(.16,1,.3,1);
 position:fixed;inset:0;overflow:hidden;background:#050505;color:var(--ink);
 font-family:Inter,system-ui,"PingFang SC",sans-serif;-webkit-font-smoothing:antialiased}
.tp-login *{box-sizing:border-box;margin:0;padding:0}
.tp-aifx{position:fixed;inset:0;z-index:0;pointer-events:none}
.tp-aifx>*{position:absolute!important;inset:0!important;width:100%!important;height:100%!important}
.tp-scrim{position:fixed;inset:0;z-index:1;pointer-events:none;
 background:linear-gradient(90deg,rgba(5,5,5,.82) 0%,rgba(5,5,5,.5) 40%,rgba(5,5,5,.12) 66%,rgba(5,5,5,.28) 100%)}
.tp-stage{position:relative;z-index:2;height:100%;display:flex;flex-direction:column}
.tp-topbar{display:flex;align-items:center;justify-content:space-between;padding:26px 56px}
.tp-brand{display:flex;align-items:center;gap:11px}
.tp-mark{width:30px;height:30px;border-radius:8px;background:rgba(255,255,255,.06);border:1px solid var(--line);
 display:grid;place-items:center;font-weight:700;font-size:12px;letter-spacing:-.02em}
.tp-wordmark{font-size:16px;font-weight:500;letter-spacing:-.01em}
.tp-topmeta{font-family:"Space Grotesk",monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:rgba(235,235,235,.35)}
.tp-hero{flex:1;width:100%;max-width:1280px;margin:0 auto;padding:0 56px 40px;
 display:grid;grid-template-columns:1.06fr .94fr;align-items:center;gap:48px}
.tp-left{max-width:620px}
.tp-eyebrow{display:flex;align-items:center;gap:10px;font-family:"Space Grotesk",monospace;font-size:11px;font-weight:500;
 letter-spacing:.24em;text-transform:uppercase;color:rgba(235,235,235,.42);margin-bottom:26px}
.tp-dot{width:7px;height:7px;border-radius:50%;background:var(--emerald);box-shadow:0 0 12px var(--emerald);animation:tp-pulse 2.2s var(--ease) infinite}
@keyframes tp-pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.65)}}
.tp-h1{font-family:"Newsreader",serif;font-weight:400;font-size:clamp(58px,7vw,108px);line-height:.94;letter-spacing:-.02em}
.tp-em{color:var(--emerald);display:block;font-style:italic;font-weight:300}
.tp-sub{margin-top:28px;font-size:16px;font-weight:300;line-height:1.7;color:rgba(235,235,235,.52);max-width:410px}
.tp-sub b{color:rgba(235,235,235,.78);font-weight:400}
.tp-compliance{display:flex;gap:26px;margin-top:44px;font-family:"Space Grotesk",monospace;font-size:11px;letter-spacing:.12em;
 text-transform:uppercase;color:rgba(235,235,235,.38)}
.tp-compliance span{display:flex;align-items:center;gap:7px}
.tp-compliance i{color:var(--emerald);font-style:normal}
.tp-right{display:flex;justify-content:flex-end}
.tp-card{position:relative;width:392px;padding:38px 36px 30px;border-radius:22px;
 background:rgba(9,11,12,.42);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
 border:1px solid var(--line);box-shadow:0 30px 90px rgba(0,0,0,.6);overflow:hidden;isolation:isolate}
.tp-card::before{content:"";position:absolute;inset:0;border-radius:inherit;z-index:-1;
 background:radial-gradient(520px circle at var(--mx,50%) var(--my,0%),rgba(16,185,129,.13),transparent 42%);
 opacity:0;transition:opacity .5s var(--ease)}
.tp-card:hover::before{opacity:1}
.tp-card::after{content:"";position:absolute;inset:-1px;border-radius:inherit;z-index:-1;padding:1px;
 background:linear-gradient(120deg,transparent 30%,rgba(16,185,129,.5) 50%,transparent 70%);background-size:250% 250%;
 -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;
 animation:tp-shim 5s linear infinite}
@keyframes tp-shim{0%{background-position:200% 0}100%{background-position:-200% 0}}
.tp-panel-eyebrow{font-family:"Space Grotesk",monospace;font-size:10px;font-weight:500;letter-spacing:.22em;text-transform:uppercase;color:rgba(235,235,235,.4);margin-bottom:8px}
.tp-panel-title{font-size:19px;font-weight:600;letter-spacing:-.01em;margin-bottom:28px}
.tp-label{display:block;font-family:"Space Grotesk",monospace;font-size:10px;font-weight:500;letter-spacing:.2em;text-transform:uppercase;color:rgba(235,235,235,.4);margin:0 0 8px 2px}
.tp-inp{width:100%;height:46px;background:rgba(255,255,255,.03);border:1px solid var(--line);border-radius:12px;color:var(--ink);
 padding:0 14px;font-size:14px;font-family:Inter,sans-serif;outline:none;transition:.25s var(--ease)}
.tp-inp::placeholder{color:rgba(235,235,235,.28)}
.tp-inp:focus{border-color:rgba(16,185,129,.6);box-shadow:0 0 0 3px rgba(16,185,129,.16);background:rgba(255,255,255,.05)}
.tp-gap{height:18px}
.tp-err{margin-top:16px;border-radius:10px;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);
 padding:9px 12px;font-size:13px;color:#fca5a5}
.tp-btn{width:100%;height:48px;margin-top:26px;background:var(--ink);color:#050505;border:0;border-radius:999px;font-size:14px;
 font-weight:600;font-family:Inter,sans-serif;letter-spacing:.01em;cursor:pointer;transition:.35s var(--ease);box-shadow:0 0 0 rgba(16,185,129,0)}
.tp-btn:hover:not(:disabled){background:#fff;transform:translateY(-1px);box-shadow:0 0 34px rgba(16,185,129,.4)}
.tp-btn:disabled{opacity:.6;cursor:default}
.tp-link{display:block;width:100%;margin-top:14px;background:none;border:0;cursor:pointer;font-family:Inter,sans-serif;
 font-size:12.5px;color:rgba(235,235,235,.5);transition:color .25s var(--ease)}
.tp-link:hover{color:var(--emerald)}
.tp-note{font-size:13.5px;line-height:1.65;color:rgba(235,235,235,.58)}
.tp-foot{margin-top:20px;font-family:"Space Grotesk",monospace;font-size:11px;letter-spacing:.03em;color:rgba(235,235,235,.32);text-align:center}
@media(max-width:920px){
 .tp-topbar{padding:20px 24px}
 .tp-hero{grid-template-columns:1fr;gap:32px;padding:0 24px 32px;align-items:start;align-content:center}
 .tp-right{justify-content:flex-start}
 .tp-card{width:100%;max-width:420px}
 .tp-h1{font-size:clamp(46px,12vw,72px)}
}
`;
