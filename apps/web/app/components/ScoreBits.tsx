// Shared presentation primitives for the multi-dimensional ranking UI.
// Deliberately plain: the point is verifiability, not visual polish.

export function Chip({
  label,
  value,
  tone = "mute",
}: {
  label: string;
  value: string;
  tone?: "good" | "warn" | "bad" | "mute" | "info";
}) {
  const tones: Record<string, string> = {
    good: "bg-emerald-950 text-emerald-300 border-emerald-800",
    warn: "bg-amber-950 text-amber-300 border-amber-800",
    bad: "bg-red-950 text-red-300 border-red-800",
    info: "bg-blue-950 text-blue-300 border-blue-900",
    mute: "bg-gray-800 text-gray-300 border-gray-700",
  };
  return (
    <span className={`text-[11px] px-2 py-0.5 rounded border ${tones[tone]}`}>
      <span className="opacity-60">{label}</span> {value}
    </span>
  );
}

export function eligibilityTone(g?: string): "good" | "warn" | "bad" | "mute" {
  if (g === "PASS") return "good";
  if (g === "REVIEW") return "warn";
  if (g === "FAIL") return "bad";
  return "mute";
}

export function tierTone(t?: string): "good" | "warn" | "mute" {
  if (!t) return "mute";
  if (t.includes("?")) return "warn"; // provisional / unrated
  if (t.startsWith("S") || t.startsWith("A")) return "good";
  return "mute";
}

/** A labelled 0-100 metric with a bar. Shows "—" when genuinely unknown. */
export function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value?: number | null;
  hint?: string;
}) {
  const known = typeof value === "number";
  return (
    <div>
      <div className="flex justify-between text-[11px] text-gray-400">
        <span>{label}</span>
        <span className="text-gray-200">{known ? value!.toFixed(0) : "—"}</span>
      </div>
      <div className="h-1.5 bg-gray-800 rounded mt-1 overflow-hidden">
        <div
          className="h-1.5 bg-accent"
          style={{ width: known ? `${Math.max(0, Math.min(100, value!))}%` : "0%" }}
        />
      </div>
      {hint && <div className="text-[10px] text-gray-600 mt-0.5">{hint}</div>}
    </div>
  );
}

export function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-gray-800 bg-panel p-4">
      <h2 className="text-sm font-semibold text-white">{title}</h2>
      {subtitle && <p className="text-[11px] text-gray-500 mt-0.5 mb-3">{subtitle}</p>}
      <div className={subtitle ? "" : "mt-3"}>{children}</div>
    </section>
  );
}
