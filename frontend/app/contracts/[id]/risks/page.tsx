"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, Clause, ClauseSummary, Risk } from "@/lib/api";
import { categoryLabel, clauseRef, sevMeta, SEV_RANK } from "@/lib/format";
import { diffWords } from "@/lib/diff";

const CATEGORY_CHIPS = [
  { key: "all", label: "All" },
  { key: "commercial", label: "Commercial" },
  { key: "legal", label: "Legal" },
  { key: "compliance", label: "Compliance" },
  { key: "delivery", label: "Delivery" },
  { key: "termination_renewal", label: "Renewal / Termination" },
];

export default function RiskPage() {
  const { id } = useParams<{ id: string }>();
  const [risks, setRisks] = useState<Risk[]>([]);
  const [clauses, setClauses] = useState<ClauseSummary[]>([]);
  const [spotlight, setSpotlight] = useState<Clause | null>(null);
  const [category, setCategory] = useState("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.risks(id), api.clauses(id)])
      .then(([r, cs]) => {
        setRisks(r);
        setClauses(cs);
        const ns = cs.find((c) => c.nonstandard);
        if (ns) api.clause(ns.clause_id).then(setSpotlight).catch(() => {});
      })
      .catch((e) => setError((e as Error).message));
  }, [id]);

  // clause_id -> {section, nonstandard} for enriching risk cards
  const clauseMap = useMemo(() => {
    const m = new Map<string, ClauseSummary>();
    clauses.forEach((c) => m.set(c.clause_id, c));
    return m;
  }, [clauses]);

  const view = useMemo(
    () =>
      risks
        .filter((r) => category === "all" || r.category === category)
        .sort((a, b) => SEV_RANK[a.severity] - SEV_RANK[b.severity]),
    [risks, category]
  );

  const counts = {
    high: risks.filter((r) => r.severity === "high").length,
    medium: risks.filter((r) => r.severity === "medium" || r.severity === "med").length,
    low: risks.filter((r) => r.severity === "low").length,
  };

  return (
    <main>
      <h1 style={{ marginBottom: 16 }}>Risk Assessment</h1>
      {error && <div className="error">{error}</div>}

      <div className="flex" style={{ gap: 16, marginBottom: 16 }}>
        <Legend n={counts.high} label="High" color="var(--sev-high)" />
        <Legend n={counts.medium} label="Medium" color="var(--sev-med)" />
        <Legend n={counts.low} label="Low" color="var(--sev-low)" />
      </div>

      <div className="wrap-chips" style={{ marginBottom: 20 }}>
        {CATEGORY_CHIPS.map((c) => (
          <button
            key={c.key}
            className={`chip-round ${category === c.key ? "chip-active" : "chip"}`}
            onClick={() => setCategory(c.key)}
          >
            {c.label}
          </button>
        ))}
      </div>

      {view.length === 0 && <p className="muted">No risks flagged.</p>}

      {view.map((r) => {
        const sev = sevMeta(r.severity);
        const cl = clauseMap.get(r.source_clause_id);
        return (
          <div key={r.id} className="card">
            <div className="flex between items-center" style={{ marginBottom: 10 }}>
              <span className="badge" style={{ color: sev.color, background: sev.bg }}>{sev.label}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>
                {categoryLabel(r.category)}
                {r.flagged_by === "rule" ? " · rule" : ""}
              </span>
            </div>
            <h3 style={{ fontSize: 17, margin: "0 0 8px" }}>{r.title}</h3>
            {r.rationale && (
              <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--muted-2)", margin: "0 0 14px" }}>{r.rationale}</p>
            )}
            <div className="flex between items-center">
              {cl?.nonstandard ? (
                <span className="chip chip-accent">Non-standard clause</span>
              ) : (
                <span />
              )}
              <Link
                href={`/clauses/${r.source_clause_id}?q=${encodeURIComponent(r.source_quote || "")}`}
                style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}
              >
                View source clause §{clauseRef(cl?.section, r.source_clause_id)} →
              </Link>
            </div>
          </div>
        );
      })}

      {spotlight && spotlight.standard_text && (
        <div className="card" style={{ marginTop: 24 }}>
          <h3>Non-standard clause detected</h3>
          <p style={{ fontSize: 12.5, color: "var(--muted)", margin: "0 0 16px" }}>
            §{clauseRef(spotlight.section, spotlight.clause_id)} {spotlight.heading || ""} — compared against the
            standard clause library.
          </p>
          {spotlight.nonstandard_explanation && (
            <p style={{ fontSize: 14, lineHeight: 1.55, margin: "0 0 16px" }}>{spotlight.nonstandard_explanation}</p>
          )}
          <SpotlightDiff standard={spotlight.standard_text} actual={spotlight.text} title={spotlight.standard_title} />
        </div>
      )}
    </main>
  );
}

function Legend({ n, label, color }: { n: number; label: string; color: string }) {
  return (
    <div className="flex items-center" style={{ gap: 6, fontSize: 13, fontWeight: 600 }}>
      <span className="dot" style={{ background: color }} />
      {n} {label}
    </div>
  );
}

function SpotlightDiff({ standard, actual, title }: { standard: string; actual: string; title?: string | null }) {
  const { left, right } = useMemo(() => diffWords(standard, actual), [standard, actual]);
  return (
    <div className="diff-grid">
      <div className="diff-pane standard">
        <div className="diff-label" style={{ color: "var(--muted)" }}>{title || "STANDARD CLAUSE LIBRARY"}</div>
        {left.map((s, i) => (s.changed ? <span key={i} className="del">{s.text} </span> : <span key={i}>{s.text} </span>))}
      </div>
      <div className="diff-pane actual">
        <div className="diff-label" style={{ color: "var(--sev-high)" }}>THIS CONTRACT</div>
        {right.map((s, i) => (s.changed ? <span key={i} className="add">{s.text} </span> : <span key={i}>{s.text} </span>))}
      </div>
    </div>
  );
}
