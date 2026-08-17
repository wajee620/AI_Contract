"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, CalendarBucket, CalendarEvent, CalendarResponse } from "@/lib/api";
import { fmtDate, typeLabel } from "@/lib/format";

const BUCKETS: Array<{ key: CalendarBucket; label: string; color: string }> = [
  { key: "overdue", label: "Overdue", color: "var(--sev-high)" },
  { key: "next_30_days", label: "Next 30 days", color: "var(--sev-med)" },
  { key: "next_90_days", label: "Next 90 days", color: "var(--link)" },
  { key: "recurring", label: "Recurring", color: "var(--muted-2)" },
  { key: "later", label: "Later", color: "var(--muted-2)" },
  { key: "unscheduled", label: "Trigger-based / unscheduled", color: "var(--muted)" },
];

export default function CalendarPage() {
  const { id } = useParams<{ id: string }>();
  const [cal, setCal] = useState<CalendarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .calendar(id)
      .then(setCal)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [id]);

  const grouped = useMemo(() => {
    const m = new Map<CalendarBucket, CalendarEvent[]>();
    (cal?.events || []).forEach((e) => {
      const arr = m.get(e.bucket) || [];
      arr.push(e);
      m.set(e.bucket, arr);
    });
    return m;
  }, [cal]);

  return (
    <main>
      <div className="flex between items-center" style={{ marginBottom: 6 }}>
        <h1 style={{ margin: 0 }}>Obligation Calendar</h1>
        <span className="chip chip-accent">Agent · LangGraph</span>
      </div>
      <p className="lead" style={{ marginTop: 6 }}>
        The calendar agent resolves relative and recurring deadlines ("within 45 days of invoice",
        "quarterly") against the contract's effective date, then buckets each obligation by urgency.
        {cal ? ` Reference date ${fmtDate(cal.reference_date)}.` : ""}
      </p>

      {error && <div className="error">{error}</div>}
      {loading && <p className="muted">Running the calendar agent…</p>}

      {cal && (
        <>
          <p className="muted" style={{ fontSize: 13, marginBottom: 18 }}>
            {cal.summary}
          </p>

          {BUCKETS.map(({ key, label, color }) => {
            const events = grouped.get(key);
            if (!events || events.length === 0) return null;
            return (
              <section key={key} style={{ marginBottom: 24 }}>
                <div className="flex items-center" style={{ gap: 8, marginBottom: 10 }}>
                  <span className="dot" style={{ background: color }} />
                  <h3 style={{ margin: 0, fontSize: 15 }}>
                    {label} <span className="muted" style={{ fontWeight: 500 }}>· {events.length}</span>
                  </h3>
                </div>
                {events.map((e) => (
                  <div key={e.obligation_id} className="card card-tight">
                    <div className="flex between items-center" style={{ gap: 12 }}>
                      <div style={{ minWidth: 0 }}>
                        <div className="flex items-center" style={{ gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                          <span className="chip chip-accent">{typeLabel(e.obligation_type)}</span>
                          <UrgencyTag urgency={e.urgency} />
                          {e.obligated_party && (
                            <span className="muted" style={{ fontSize: 12.5 }}>{e.obligated_party}</span>
                          )}
                        </div>
                        <div style={{ fontSize: 14, lineHeight: 1.5 }}>{e.title}</div>
                        {e.note && (
                          <div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>↳ {e.note}</div>
                        )}
                      </div>
                      <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>
                          {e.resolved_date ? fmtDate(e.resolved_date) : e.raw_due || "—"}
                        </div>
                        <Link
                          href={`/clauses/${e.source_clause_id}`}
                          style={{ fontSize: 12.5, fontWeight: 600, color: "var(--muted)" }}
                        >
                          source →
                        </Link>
                      </div>
                    </div>
                  </div>
                ))}
              </section>
            );
          })}

          {cal.events.length === 0 && <p className="muted">No obligations found for this contract.</p>}
        </>
      )}
    </main>
  );
}

function UrgencyTag({ urgency }: { urgency: "high" | "medium" | "low" }) {
  const map = {
    high: { label: "High", color: "var(--sev-high)", bg: "var(--sev-high-bg)" },
    medium: { label: "Medium", color: "var(--sev-med)", bg: "var(--sev-med-bg)" },
    low: { label: "Low", color: "var(--muted)", bg: "var(--surface-2)" },
  }[urgency];
  return (
    <span className="badge" style={{ color: map.color, background: map.bg }}>
      {map.label}
    </span>
  );
}
