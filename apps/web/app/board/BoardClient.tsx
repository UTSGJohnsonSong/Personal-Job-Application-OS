"use client";

import { useMemo, useState } from "react";

import { queueAdd, queueRemove, scorePending } from "@/app/actions";
import {
  GlobalRole,
  POSTURE_HELP,
  POSTURE_LABEL,
  Posture,
  RegisterCompany,
  RoleDetail,
  board,
  reachOf,
} from "@/lib/board";

/* Weights live in app/ranking/modes.py. Printed next to each dimension so the
   number on the right is always reconstructable from what is on screen. */
const DIMS: { key: string; label: string; weight: number }[] = [
  { key: "company_platform_value", label: "Company platform", weight: 0.38 },
  { key: "role_strategic_value", label: "Role direction", weight: 0.2 },
  { key: "team_project_quality", label: "Team and project", weight: 0.15 },
  { key: "current_candidate_fit", label: "Your fit today", weight: 0.11 },
  { key: "career_optionality", label: "What it opens", weight: 0.1 },
  { key: "opportunity_viability", label: "Still live", weight: 0.06 },
];

const TIERS = ["S", "A", "B", "C", "D"];

export function BoardClient({
  roles,
  register,
  queued,
}: {
  roles: GlobalRole[];
  register: RegisterCompany[];
  queued: string[];
}) {
  const [view, setView] = useState<"roles" | "companies">("roles");
  const [openRole, setOpenRole] = useState<string | null>(null);
  const [openCo, setOpenCo] = useState<string | null>(null);
  const [detail, setDetail] = useState<Record<string, RoleDetail | "loading" | "error">>({});
  const [canadaOnly, setCanadaOnly] = useState(false);
  const [hideReview, setHideReview] = useState(false);
  const [showAllPerEmployer, setShowAllPerEmployer] = useState(false);
  const [shortlist, setShortlist] = useState<Set<string>>(new Set(queued));
  const [saving, setSaving] = useState<string | null>(null);
  const [scoring, setScoring] = useState<string | null>(null);

  /** Loop the slice endpoint until nothing is left unscored.
   *  One request cannot cover ten thousand postings without a proxy cutting it
   *  off, and each slice commits, so an interruption here costs one slice. */
  async function runScoring() {
    let done = 0;
    try {
      for (;;) {
        setScoring(done ? `Scored ${done}…` : "Starting…");
        const r = await scorePending(400);
        done += r.scored;
        if (r.remaining === 0 || r.scored === 0) break;
      }
      setScoring(`Scored ${done} — reloading`);
      window.location.reload();
    } catch (e) {
      setScoring(null);
      alert(`Scoring stopped after ${done}: ${(e as Error).message}`);
    }
  }

  /** Writes through to the real apply queue, then reflects it locally.
   *  On failure the row snaps back rather than showing a save that did not
   *  happen — a list that lies about what is on it is worse than an error. */
  async function toggleQueue(jobId: string) {
    const on = shortlist.has(jobId);
    setSaving(jobId);
    const fd = new FormData();
    fd.set("job_id", jobId);
    try {
      await (on ? queueRemove(fd) : queueAdd(fd));
      setShortlist((s) => {
        const n = new Set(s);
        on ? n.delete(jobId) : n.add(jobId);
        return n;
      });
    } catch {
      setSaving(null);
      alert("Could not reach the API — the list was not changed.");
      return;
    }
    setSaving(null);
  }

  const postureOf = useMemo(() => {
    const m: Record<string, Posture> = {};
    for (const c of register) m[c.name] = c.posture;
    return m;
  }, [register]);

  /* At most three roles from any one employer, unless asked otherwise.
     One company with an open board can hold hundreds of postings — a flat
     priority list then becomes that company's careers page. You are not going
     to send six applications to the same employer anyway, so the rest are
     noise here; they stay one click away under Employers. */
  const PER_EMPLOYER = 3;
  const { shown, hidden } = useMemo(() => {
    const passing = roles.filter(
      (r) =>
        (!canadaOnly || reachOf(r.location) === "ca") &&
        (!hideReview || r.eligibility === "PASS"),
    );
    if (showAllPerEmployer) return { shown: passing, hidden: 0 };
    const seen: Record<string, number> = {};
    const kept: GlobalRole[] = [];
    let dropped = 0;
    for (const r of passing) {
      const n = (seen[r.company] ?? 0) + 1;
      seen[r.company] = n;
      if (n <= PER_EMPLOYER) kept.push(r);
      else dropped++;
    }
    return { shown: kept, hidden: dropped };
  }, [roles, canadaOnly, hideReview, showAllPerEmployer]);

  async function toggleRole(jobId: string) {
    if (openRole === jobId) return setOpenRole(null);
    setOpenRole(jobId);
    if (detail[jobId]) return;
    setDetail((d) => ({ ...d, [jobId]: "loading" }));
    try {
      const got = await board.detail(jobId);
      setDetail((d) => ({ ...d, [jobId]: got }));
    } catch {
      setDetail((d) => ({ ...d, [jobId]: "error" }));
    }
  }

  const refer = register.filter((c) => c.posture === "worth_forcing");

  return (
    <div className="bd">
      <style>{CSS}</style>

      {/* Postings can be in the database with no score yet — an interrupted
          scoring pass leaves exactly that, and unscored roles never reach this
          list. Rather than showing an empty board with no explanation, offer
          the thing that fixes it. */}
      {roles.length < 20 && (
        <div className="prompt">
          <div>
            <b>Only {roles.length} scored role{roles.length === 1 ? "" : "s"}.</b>{" "}
            {register.length} employers are on the register, so if the inbox counts
            thousands of open roles, they are in the database but unscored — an
            interrupted scoring pass leaves them that way and they cannot be ranked
            until it finishes.
          </div>
          <button className="btn" onClick={runScoring} disabled={!!scoring}>
            {scoring ?? "Score them now"}
          </button>
        </div>
      )}

      <header className="bd-head">
        <div>
          <h1>Board</h1>
          <p>
            {roles.length} roles ranked by priority · {register.length} employers on the
            register
          </p>
        </div>
        <div className="seg" role="tablist">
          <button
            role="tab"
            aria-selected={view === "roles"}
            onClick={() => setView("roles")}
          >
            Roles
          </button>
          <button
            role="tab"
            aria-selected={view === "companies"}
            onClick={() => setView("companies")}
          >
            Employers
          </button>
        </div>
      </header>

      {view === "roles" && (
        <>
          <div className="toolbar">
            <Toggle on={canadaOnly} set={setCanadaOnly} label="Canada only" />
            <Toggle on={hideReview} set={setHideReview} label="Ready to apply only" />
            {(hidden > 0 || showAllPerEmployer) && (
              <Toggle
                on={showAllPerEmployer}
                set={setShowAllPerEmployer}
                label={
                  showAllPerEmployer
                    ? "Top 3 per employer"
                    : `Show ${hidden} more from the same employers`
                }
              />
            )}
            <span className="count">
              {shown.length} shown
              {!showAllPerEmployer && hidden > 0 && (
                <span className="cap"> · top {PER_EMPLOYER} per employer</span>
              )}
              {shortlist.size > 0 && (
                <>
                  {" · "}
                  <a href="/queue">{shortlist.size} on your apply list</a>
                </>
              )}
            </span>
          </div>

          <ol className="list">
            {shown.map((r, i) => {
              const posture = postureOf[r.company] ?? "balanced";
              const open = openRole === r.job_id;
              const listed = shortlist.has(r.job_id);
              return (
                <li
                  key={r.job_id}
                  className={`row${open ? " open" : ""}${listed ? " listed" : ""}`}
                >
                  <button className="row-main" onClick={() => toggleRole(r.job_id)}>
                    <span className="rank">{listed ? "✓" : i + 1}</span>
                    <span className="who">
                      <span className="co">{r.company}</span>
                      <span className="tier">{r.company_tier}</span>
                      {posture !== "balanced" && (
                        <span className={`pos ${posture}`}>{POSTURE_LABEL[posture]}</span>
                      )}
                      <span className="title">{r.title}</span>
                    </span>
                    <span className={`reach ${reachOf(r.location)}`}>
                      {r.location || "Location not stated"}
                    </span>
                    <span className={`gate ${r.eligibility.toLowerCase()}`}>
                      {r.eligibility === "PASS" ? "Ready" : "Needs a look"}
                    </span>
                    <span className="score">{r.application_priority.toFixed(0)}</span>
                    <span className="chev" aria-hidden>
                      {open ? "▲" : "▼"}
                    </span>
                  </button>

                  {open && (
                    <Detail
                      role={r}
                      posture={posture}
                      state={detail[r.job_id]}
                      onShortlist={() => toggleQueue(r.job_id)}
                      listed={shortlist.has(r.job_id)}
                      saving={saving === r.job_id}
                    />
                  )}
                </li>
              );
            })}
          </ol>
        </>
      )}

      {view === "companies" && (
        <>
          {refer.length > 0 && (
            <section className="grp refer">
              <h2>
                Worth a referral <span>{refer.length}</span>
              </h2>
              <p className="grp-note">
                Worth far more than they are reachable. Ranked by value, not by tier —
                tier is what buries them, since it multiplies value by reach.
              </p>
              {[...refer]
                .sort((a, b) => b.value - a.value)
                .map((c) => (
                  <CompanyRow
                    key={c.key}
                    c={c}
                    roles={roles}
                    open={openCo === c.key}
                    onToggle={() => setOpenCo(openCo === c.key ? null : c.key)}
                  />
                ))}
            </section>
          )}

          {TIERS.map((t) => {
            const cs = register.filter(
              (c) => c.tier === t && c.posture !== "worth_forcing",
            );
            if (!cs.length) return null;
            const hiring = cs.filter((c) => c.open_roles > 0).length;
            return (
              <section className="grp" key={t}>
                <h2>
                  Tier {t} <span>{cs.length}</span>
                </h2>
                <p className="grp-note">
                  {hiring} hiring now ·{" "}
                  {cs.reduce((a, c) => a + c.open_roles, 0)} open roles
                </p>
                {cs
                  .sort((a, b) => b.score - a.score)
                  .map((c) => (
                    <CompanyRow
                      key={c.key}
                      c={c}
                      roles={roles}
                      open={openCo === c.key}
                      onToggle={() => setOpenCo(openCo === c.key ? null : c.key)}
                    />
                  ))}
              </section>
            );
          })}
        </>
      )}
    </div>
  );
}

function Toggle({
  on,
  set,
  label,
}: {
  on: boolean;
  set: (v: boolean) => void;
  label: string;
}) {
  return (
    <button className={on ? "tg on" : "tg"} aria-pressed={on} onClick={() => set(!on)}>
      {label}
    </button>
  );
}

/** Everything below the fold of a row. Fetched on open, never before. */
function Detail({
  role,
  posture,
  state,
  onShortlist,
  listed,
  saving,
}: {
  role: GlobalRole;
  posture: Posture;
  state: RoleDetail | "loading" | "error" | undefined;
  onShortlist: () => void;
  listed: boolean;
  saving: boolean;
}) {
  return (
    <div className="detail">
      {posture === "worth_forcing" && (
        <p className="warn">{POSTURE_HELP[posture]}</p>
      )}

      {state === "loading" && <p className="dim">Loading the breakdown…</p>}
      {state === "error" && <p className="dim">Could not load the breakdown.</p>}
      {state && state !== "loading" && state !== "error" && (
        <>
          <h3>How this score is made</h3>
          <div className="dims">
            {DIMS.map((d) => {
              const raw = Number(state.scores?.[d.key] ?? NaN);
              const has = Number.isFinite(raw);
              const pts = has ? raw * d.weight : 0;
              return (
                <div className="dim" key={d.key}>
                  <span className="dl">{d.label}</span>
                  <span className="dtrack">
                    <span className="dfill" style={{ width: `${has ? raw : 0}%` }} />
                  </span>
                  <span className="dv">{has ? raw.toFixed(0) : "—"}</span>
                  <span className="dw">
                    × {(d.weight * 100).toFixed(0)}% = {has ? pts.toFixed(1) : "—"}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="total">
            <b>{state.why_it_ranks_here.final_priority.toFixed(1)}</b> out of 100 — a
            weighted sum, not a match percentage.
          </p>
        </>
      )}

      <div className="acts">
        <button
          className={listed ? "btn on" : "btn"}
          onClick={onShortlist}
          disabled={saving}
        >
          {saving ? "Saving…" : listed ? "On your apply list ✓" : "Add to apply list"}
        </button>
        {role.apply_url && (
          <a className="btn ghost" href={role.apply_url} target="_blank" rel="noreferrer">
            Open the posting
          </a>
        )}
        <a className="btn ghost" href={`/rankings/${role.job_id}`}>
          Full explanation
        </a>
        {listed && (
          <a className="btn ghost" href="/queue">
            Go to the apply list
          </a>
        )}
      </div>
    </div>
  );
}

function CompanyRow({
  c,
  roles,
  open,
  onToggle,
}: {
  c: RegisterCompany;
  roles: GlobalRole[];
  open: boolean;
  onToggle: () => void;
}) {
  const mine = roles.filter((r) => r.company === c.name);
  return (
    <div className={open ? "crow open" : "crow"}>
      <button className="crow-main" onClick={onToggle}>
        <span className="co">{c.name}</span>
        <span className="tier">{c.tier}</span>
        {c.posture !== "balanced" && (
          <span className={`pos ${c.posture}`}>{POSTURE_LABEL[c.posture]}</span>
        )}
        <span className="spacer" />
        <span className="pair">
          <em>Worth</em>
          {c.value.toFixed(0)}
        </span>
        <span className="pair">
          <em>Reach</em>
          {c.access.toFixed(0)}
        </span>
        <span className="pair">
          <em>Open</em>
          {c.open_roles}
        </span>
        <span className="chev" aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </button>
      {open && (
        <div className="cdetail">
          {c.why && <p className="why">{c.why}</p>}
          {c.posture !== "balanced" && <p className="warn">{POSTURE_HELP[c.posture]}</p>}
          {mine.length > 0 ? (
            <ul className="croles">
              {mine.map((r) => (
                <li key={r.job_id}>
                  <a href={`/rankings/${r.job_id}`}>{r.title}</a>
                  <span className={`gate ${r.eligibility.toLowerCase()}`}>
                    {r.eligibility === "PASS" ? "Ready" : "Needs a look"}
                  </span>
                  <b>{r.application_priority.toFixed(0)}</b>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dim">
              {c.open_roles > 0
                ? `${c.open_roles} open, none in the top ${roles.length} by priority.`
                : "Nothing open right now."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* Scoped so nothing here depends on the global Tailwind scale, which redefines
   `white` as ink and runs the grey ramp backwards. Plain values, honest names. */
const CSS = `
.bd{
  --paper:#f5f5f7; --card:#ffffff;
  --ink:#1d1d1f; --ink-2:#6e6e73; --ink-3:#86868b;
  --line:rgba(0,0,0,.08); --line-2:rgba(0,0,0,.05);
  --blue:#0071e3; --green:#1d7a4c; --amber:#8a6100;
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",system-ui,sans-serif;
  letter-spacing:-.011em;
  max-width:1120px;
}
.bd h1{font-size:26px;font-weight:600;letter-spacing:-.022em}
.bd-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;
  flex-wrap:wrap;margin-bottom:22px}
.bd-head p{color:var(--ink-2);font-size:13px;margin-top:3px}

.seg{display:inline-flex;background:rgba(0,0,0,.05);border-radius:9px;padding:2px}
.seg button{border:0;background:none;font:inherit;font-size:13px;font-weight:500;
  color:var(--ink-2);padding:5px 15px;border-radius:7px;cursor:pointer}
.seg button[aria-selected="true"]{background:var(--card);color:var(--ink);
  box-shadow:0 1px 3px rgba(0,0,0,.10)}

.toolbar{display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.tg{font:inherit;font-size:12.5px;padding:5px 13px;border-radius:999px;cursor:pointer;
  border:1px solid var(--line);background:var(--card);color:var(--ink-2)}
.tg:hover{color:var(--ink)}
.tg.on{background:var(--ink);border-color:var(--ink);color:#fff}
.toolbar .count{margin-left:auto;font-size:12.5px;color:var(--ink-3)}

.list{list-style:none;background:var(--card);border-radius:14px;overflow:hidden;
  box-shadow:0 1px 2px rgba(0,0,0,.04),0 8px 26px -18px rgba(0,0,0,.22)}
.row{border-bottom:1px solid var(--line-2)}
.row:last-child{border-bottom:0}
.row.open{background:#fbfbfd}
.row.listed .rank{color:var(--blue);font-weight:700}
.row.listed{box-shadow:inset 3px 0 0 var(--blue)}
.prompt{display:flex;align-items:center;gap:16px;background:var(--card);
  border:1px solid var(--line);border-left:3px solid var(--blue);border-radius:12px;
  padding:14px 18px;margin-bottom:20px;font-size:13px;color:var(--ink-2);line-height:1.55}
.prompt b{color:var(--ink)}
.prompt .btn{white-space:nowrap}
.toolbar .count .cap{color:var(--ink-3)}
.toolbar .count a{color:var(--blue);text-decoration:none}
.toolbar .count a:hover{text-decoration:underline}
.btn:disabled{opacity:.55;cursor:default}
.row-main{width:100%;display:grid;
  grid-template-columns:34px minmax(0,1fr) 168px 104px 46px 22px;
  gap:14px;align-items:center;padding:13px 18px;background:none;border:0;
  font:inherit;text-align:left;cursor:pointer}
.row-main:hover{background:rgba(0,0,0,.02)}
.rank{color:var(--ink-3);font-size:12px;font-variant-numeric:tabular-nums}
.who{min-width:0}
.co{font-weight:600;font-size:14px}
.tier{font-size:10.5px;font-weight:600;color:var(--ink-3);border:1px solid var(--line);
  border-radius:4px;padding:0 5px;margin-left:7px;vertical-align:1px}
.pos{font-size:10.5px;font-weight:600;border-radius:4px;padding:1px 6px;margin-left:6px;
  vertical-align:1px}
.pos.worth_forcing{color:var(--blue);background:rgba(0,113,227,.10)}
.pos.floor_only{color:var(--ink-3);background:rgba(0,0,0,.05)}
.title{display:block;color:var(--ink-2);font-size:13px;margin-top:2px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.reach{font-size:12px;color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.reach.ca{color:var(--green)}
.reach.intl{color:var(--ink-3)}
.gate{font-size:12px;font-weight:500}
.gate.pass{color:var(--green)} .gate.review{color:var(--amber)}
.score{font-size:17px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums;
  letter-spacing:-.02em}
.chev{color:var(--ink-3);font-size:9px;text-align:right}

.detail{padding:4px 18px 20px 66px;border-top:1px solid var(--line-2)}
.detail h3{font-size:12px;font-weight:600;color:var(--ink-3);text-transform:uppercase;
  letter-spacing:.05em;margin:14px 0 10px}
.warn{background:rgba(0,113,227,.07);border-radius:9px;padding:10px 13px;font-size:13px;
  color:var(--ink);margin-top:14px;max-width:72ch;line-height:1.5}
.dim{color:var(--ink-3);font-size:13px;margin-top:12px}
.dims{display:grid;gap:7px;max-width:640px}
.dims .dim{display:grid;grid-template-columns:120px 1fr 32px 120px;gap:11px;
  align-items:center;color:inherit;font-size:12.5px;margin:0}
.dl{color:var(--ink-2)}
.dtrack{height:5px;background:rgba(0,0,0,.06);border-radius:3px;overflow:hidden}
.dfill{display:block;height:100%;background:var(--blue);border-radius:3px}
.dv{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.dw{color:var(--ink-3);font-variant-numeric:tabular-nums;font-size:11.5px}
.total{margin-top:12px;font-size:13px;color:var(--ink-2)}
.total b{color:var(--ink);font-size:15px}

.acts{display:flex;gap:9px;margin-top:16px;flex-wrap:wrap}
.btn{font:inherit;font-size:13px;font-weight:500;padding:7px 15px;border-radius:8px;
  border:1px solid transparent;background:var(--blue);color:#fff;cursor:pointer;
  text-decoration:none;display:inline-block}
.btn.on{background:var(--ink)}
.btn.ghost{background:var(--card);border-color:var(--line);color:var(--ink)}
.btn.ghost:hover{border-color:var(--ink-3)}

.grp{margin-bottom:26px}
.grp h2{font-size:15px;font-weight:600;display:flex;align-items:baseline;gap:8px}
.grp h2 span{font-size:12px;color:var(--ink-3);font-weight:500}
.grp-note{font-size:12.5px;color:var(--ink-3);margin:3px 0 10px;max-width:72ch;
  line-height:1.5}
.grp.refer h2{color:var(--blue)}

.crow{background:var(--card);border-radius:12px;margin-bottom:7px;
  box-shadow:0 1px 2px rgba(0,0,0,.04)}
.crow-main{width:100%;display:flex;align-items:center;gap:8px;padding:12px 16px;
  background:none;border:0;font:inherit;text-align:left;cursor:pointer}
.crow-main:hover{background:rgba(0,0,0,.02);border-radius:12px}
.spacer{flex:1}
.pair{font-size:12px;color:var(--ink);font-variant-numeric:tabular-nums;white-space:nowrap}
.pair em{font-style:normal;color:var(--ink-3);margin-right:5px;font-size:11px}
.cdetail{padding:2px 16px 16px 16px;border-top:1px solid var(--line-2)}
.why{font-size:13px;color:var(--ink-2);margin-top:12px;line-height:1.55;max-width:74ch}
.croles{list-style:none;margin-top:12px}
.croles li{display:flex;align-items:center;gap:12px;padding:7px 0;
  border-bottom:1px solid var(--line-2);font-size:13px}
.croles li:last-child{border-bottom:0}
.croles a{color:var(--ink);text-decoration:none;flex:1;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.croles a:hover{color:var(--blue)}
.croles b{font-variant-numeric:tabular-nums;width:30px;text-align:right}

@media (max-width:820px){
  .row-main{grid-template-columns:26px minmax(0,1fr) 56px 20px;gap:10px;padding:12px 14px}
  .reach,.gate{display:none}
  .detail{padding-left:14px}
  .dims .dim{grid-template-columns:96px 1fr 30px;}
  .dw{display:none}
  .pair:nth-of-type(2){display:none}
}
`;
