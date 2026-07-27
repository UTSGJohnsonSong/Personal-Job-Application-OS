"use client";

import { useEffect, useState } from "react";

/**
 * What the browser gets while a page's data is still being fetched.
 *
 * Next.js server-renders these pages, so nothing at all reaches the browser
 * until every API call has answered — the window simply sits on the previous
 * page and looks frozen. A `loading.tsx` puts this on screen the moment a
 * navigation starts, which turns "the app hung" into "the app is working".
 *
 * The wake notice matters more than the shimmer. The API sleeps after fifteen
 * idle minutes on the free plan and takes about fifty seconds to come back;
 * without saying so, a cold start is indistinguishable from a crash, and the
 * natural response is to reload — which starts the wait over.
 */
export function Skeleton({ rows = 8, label }: { rows?: number; label?: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="sk">
      <style>{CSS}</style>
      <div className="sk-head">
        <div className="sk-title" />
        {label && <span className="sk-label">{label}</span>}
      </div>

      {seconds >= 4 && (
        <p className="sk-note">
          {seconds < 12
            ? "Still loading — the API is on a free plan and sleeps after fifteen idle minutes."
            : `Waking the API. A cold start takes about fifty seconds; ${seconds}s so far. Reloading restarts the wait, so it is worth sitting through.`}
        </p>
      )}

      <div className="sk-list">
        {Array.from({ length: rows }, (_, i) => (
          <div className="sk-row" key={i} style={{ opacity: 1 - i * 0.07 }}>
            <div className="sk-bar w-lg" />
            <div className="sk-bar w-sm" />
          </div>
        ))}
      </div>
    </div>
  );
}

const CSS = `
.sk{max-width:1120px;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",system-ui,sans-serif}
.sk-head{display:flex;align-items:center;gap:14px;margin-bottom:20px}
.sk-title{height:26px;width:180px;border-radius:7px;background:rgba(0,0,0,.07)}
.sk-label{font-size:13px;color:#86868b}
.sk-note{font-size:12.5px;color:#6e6e73;background:#fff;border:1px solid rgba(0,0,0,.08);
  border-left:3px solid #0071e3;border-radius:10px;padding:11px 14px;margin-bottom:16px;
  max-width:72ch;line-height:1.55}
.sk-list{background:#fff;border-radius:14px;overflow:hidden;
  box-shadow:0 1px 2px rgba(0,0,0,.04),0 8px 26px -18px rgba(0,0,0,.22)}
.sk-row{display:flex;align-items:center;gap:16px;padding:15px 18px;
  border-bottom:1px solid rgba(0,0,0,.05)}
.sk-row:last-child{border-bottom:0}
.sk-bar{height:11px;border-radius:6px;
  background:linear-gradient(90deg,rgba(0,0,0,.06) 25%,rgba(0,0,0,.10) 37%,rgba(0,0,0,.06) 63%);
  background-size:400% 100%;animation:sk-shimmer 1.4s ease infinite}
.sk-bar.w-lg{flex:1;max-width:420px}
.sk-bar.w-sm{width:64px}
@keyframes sk-shimmer{0%{background-position:100% 50%}100%{background-position:0 50%}}
@media (prefers-reduced-motion:reduce){.sk-bar{animation:none}}
`;
