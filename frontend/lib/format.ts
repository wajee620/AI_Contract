// Presentation helpers shared across views — labels, date math, and the
// severity/status colour system (mirrors design/Contract Assistant.dc.html but
// normalised to the backend's enums: severity is "medium", not "med").

const ISO = /^\d{4}-\d{2}-\d{2}/;

function parseDate(s?: string | null): Date | null {
  if (!s) return null;
  const d = new Date(ISO.test(s) ? s.slice(0, 10) + "T00:00:00" : s);
  return isNaN(d.getTime()) ? null : d;
}

/** Format a due-date string; falls back to the raw string when it isn't a real date. */
export function fmtDate(s?: string | null): string {
  if (!s) return "—";
  const d = parseDate(s);
  if (!d) return s;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** Whole days from today until the given date (negative = past). null if unparseable. */
export function daysUntil(s?: string | null): number | null {
  const d = parseDate(s);
  if (!d) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86_400_000);
}

export interface SevMeta {
  key: "high" | "medium" | "low";
  label: string;
  color: string;
  bg: string;
}

export function sevMeta(severity: string): SevMeta {
  const s = severity === "med" ? "medium" : severity;
  if (s === "high") return { key: "high", label: "High", color: "var(--sev-high)", bg: "var(--sev-high-bg)" };
  if (s === "low") return { key: "low", label: "Low", color: "var(--sev-low)", bg: "var(--sev-low-bg)" };
  return { key: "medium", label: "Medium", color: "var(--sev-med)", bg: "var(--sev-med-bg)" };
}

export const SEV_RANK: Record<string, number> = { high: 0, medium: 1, med: 1, low: 2 };

export interface StatusMeta {
  label: string;
  color: string;
  bg: string;
}

/** Derive an obligation status pill from its due date (design's rules). */
export function obligationStatus(due?: string | null): StatusMeta {
  const days = daysUntil(due);
  if (days === null) return { label: "Ongoing", color: "var(--muted)", bg: "var(--surface-2)" };
  if (days < 0) return { label: "Overdue", color: "var(--sev-high)", bg: "var(--sev-high-bg)" };
  if (days <= 30) return { label: "Due soon", color: "var(--sev-med)", bg: "var(--sev-med-bg)" };
  return { label: "Upcoming", color: "var(--muted-2)", bg: "var(--surface-2)" };
}

/** Human label for the due column when there's no calendar date. */
export function dueLabel(due?: string | null, type?: string): string {
  if (due) return fmtDate(due);
  return type === "termination" || type === "renewal" ? "Notice-based" : "Trigger-based";
}

const TYPE_LABELS: Record<string, string> = {
  payment: "Payment",
  delivery: "Delivery",
  reporting: "Reporting",
  compliance: "Compliance",
  data_protection: "Data Protection",
  renewal: "Renewal",
  termination: "Termination",
  other: "Other",
};

const CATEGORY_LABELS: Record<string, string> = {
  commercial: "Commercial",
  legal: "Legal",
  compliance: "Compliance",
  delivery: "Delivery",
  termination_renewal: "Renewal / Termination",
};

export function typeLabel(t: string): string {
  return TYPE_LABELS[t] || t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function categoryLabel(c: string): string {
  return CATEGORY_LABELS[c] || c.replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
}

/** A clause's display reference — the section number if present, else the id. */
export function clauseRef(section?: string | null, clauseId?: string): string {
  return section || clauseId || "?";
}
