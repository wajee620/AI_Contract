"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, Obligation } from "@/lib/api";
import { daysUntil, dueLabel, obligationStatus, typeLabel } from "@/lib/format";

const TYPE_CHIPS = [
  { key: "all", label: "All" },
  { key: "payment", label: "Payment" },
  { key: "delivery", label: "Delivery" },
  { key: "reporting", label: "Reporting" },
  { key: "compliance", label: "Compliance" },
  { key: "data_protection", label: "Data Protection" },
  { key: "renewal", label: "Renewal" },
  { key: "termination", label: "Termination" },
];

const COLS = "2.2fr 0.9fr 1fr 1fr 1fr";

export default function TrackerPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [rows, setRows] = useState<Obligation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("all");
  const [dueSoonOnly, setDueSoonOnly] = useState(false);
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    api
      .obligations(id)
      .then(setRows)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoaded(true));
  }, [id]);

  const view = useMemo(() => {
    let v = rows.filter((o) => typeFilter === "all" || o.obligation_type === typeFilter);
    if (dueSoonOnly) {
      v = v.filter((o) => {
        const d = daysUntil(o.due_date);
        return d !== null && d <= 90;
      });
    }
    return [...v].sort((a, b) => {
      const da = daysUntil(a.due_date);
      const db = daysUntil(b.due_date);
      if (da === null && db === null) return 0;
      if (da === null) return 1; // undated sink to the bottom
      if (db === null) return -1;
      return sortAsc ? da - db : db - da;
    });
  }, [rows, typeFilter, dueSoonOnly, sortAsc]);

  return (
    <main>
      <h1 style={{ marginBottom: 20 }}>Obligation Tracker</h1>
      {error && <div className="error">{error}</div>}

      <div className="wrap-chips" style={{ marginBottom: 16 }}>
        {TYPE_CHIPS.map((c) => (
          <button
            key={c.key}
            className={`chip-round ${typeFilter === c.key ? "chip-active" : "chip"}`}
            onClick={() => setTypeFilter(c.key)}
          >
            {c.label}
          </button>
        ))}
        <button
          className={`chip-round ${dueSoonOnly ? "chip-active" : "chip"}`}
          onClick={() => setDueSoonOnly((v) => !v)}
        >
          Due within 90 days
        </button>
      </div>

      <div className="table">
        <div className="table-head" style={{ gridTemplateColumns: COLS }}>
          <div>Obligation</div>
          <div>Party</div>
          <div>Type</div>
          <div className="sortable" onClick={() => setSortAsc((v) => !v)}>
            Due {sortAsc ? "↑" : "↓"}
          </div>
          <div>Status</div>
        </div>

        {view.map((o) => {
          const st = obligationStatus(o.due_date);
          return (
            <div
              key={o.id}
              className="table-row"
              style={{ gridTemplateColumns: COLS }}
              onClick={() =>
                router.push(`/clauses/${o.source_clause_id}?q=${encodeURIComponent(o.source_quote || "")}`)
              }
            >
              <div>
                <div style={{ fontWeight: 600, marginBottom: 2 }}>{o.description}</div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>
                  {o.trigger ? o.trigger : "view source clause →"}
                </div>
              </div>
              <div className="muted-2">{o.obligated_party || "—"}</div>
              <div className="muted-2">{typeLabel(o.obligation_type)}</div>
              <div className="muted-2">{dueLabel(o.due_date, o.obligation_type)}</div>
              <div>
                <span className="badge" style={{ color: st.color, background: st.bg }}>{st.label}</span>
              </div>
            </div>
          );
        })}
      </div>

      {loaded && view.length === 0 && (
        <div style={{ textAlign: "center", padding: 40, color: "var(--muted)" }}>
          {rows.length === 0 ? "No obligations extracted yet." : "No obligations match these filters."}
        </div>
      )}
      <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>Click any row to jump to the highlighted source clause.</p>
    </main>
  );
}
