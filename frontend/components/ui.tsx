import { sevMeta, typeLabel } from "@/lib/format";

/** Coloured dot + label for a risk severity. */
export function SeverityBadge({ severity }: { severity: string }) {
  const s = sevMeta(severity);
  return (
    <span className="badge" style={{ color: s.color, background: s.bg }}>
      {s.label}
    </span>
  );
}

/** Small dot used in legends / list rows. */
export function SeverityDot({ severity, style }: { severity: string; style?: React.CSSProperties }) {
  const s = sevMeta(severity);
  return <span className="dot" style={{ background: s.color, ...style }} />;
}

/** Ingest pipeline status pill (queued/parsing/.../done/failed). */
export function StatusChip({ status, progress }: { status: string; progress?: string | null }) {
  if (status === "done")
    return (
      <span className="badge" style={{ color: "var(--sev-low)", background: "var(--sev-low-bg)" }}>
        Indexed
      </span>
    );
  if (status === "failed")
    return (
      <span
        className="badge"
        style={{ color: "var(--sev-high)", background: "var(--sev-high-bg)" }}
        title={progress || undefined}
      >
        Failed
      </span>
    );
  return (
    <span className="badge" style={{ color: "var(--sev-med)", background: "var(--sev-med-bg)" }}>
      <span className="spinner" /> {progress || status}
    </span>
  );
}

/** Obligation / clause-type chip. */
export function TypeChip({ type }: { type: string }) {
  return <span className="chip chip-accent">{typeLabel(type)}</span>;
}
