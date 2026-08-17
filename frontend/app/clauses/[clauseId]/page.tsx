"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { api, Clause, ClauseSummary, Obligation, Risk } from "@/lib/api";
import AppHeader from "@/components/AppHeader";
import { TypeChip } from "@/components/ui";
import { clauseRef, dueLabel, sevMeta, typeLabel } from "@/lib/format";
import { diffWords } from "@/lib/diff";

/** Highlight the first case-insensitive occurrence of `quote` inside the clause text. */
function HighlightedText({ text, quote }: { text: string; quote: string }) {
  const segments = useMemo(() => {
    const q = quote.trim();
    if (q.length < 4) return [{ text, mark: false }];
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return [{ text, mark: false }];
    return [
      { text: text.slice(0, idx), mark: false },
      { text: text.slice(idx, idx + q.length), mark: true },
      { text: text.slice(idx + q.length), mark: false },
    ];
  }, [text, quote]);
  return (
    <div className="clause-box">
      {segments.map((s, i) => (s.mark ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>))}
    </div>
  );
}

function SideBySideDiff({ standard, actual, title }: { standard: string; actual: string; title?: string | null }) {
  const { left, right } = useMemo(() => diffWords(standard, actual), [standard, actual]);
  return (
    <>
      <div className="diff-label" style={{ color: "var(--muted)" }}>{title || "STANDARD"}</div>
      <div className="diff-pane standard" style={{ marginBottom: 12 }}>
        {left.map((s, i) => (s.changed ? <span key={i} className="del">{s.text} </span> : <span key={i}>{s.text} </span>))}
      </div>
      <div className="diff-label" style={{ color: "var(--sev-high)" }}>THIS CONTRACT</div>
      <div className="diff-pane actual">
        {right.map((s, i) => (s.changed ? <span key={i} className="add">{s.text} </span> : <span key={i}>{s.text} </span>))}
      </div>
    </>
  );
}

function ClauseDetail() {
  const { clauseId } = useParams<{ clauseId: string }>();
  const router = useRouter();
  const quote = useSearchParams().get("q") || "";
  const [clause, setClause] = useState<Clause | null>(null);
  const [siblings, setSiblings] = useState<ClauseSummary[]>([]);
  const [obligations, setObligations] = useState<Obligation[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setClause(null);
    api
      .clause(clauseId)
      .then((c) => {
        setClause(c);
        return Promise.all([api.clauses(c.contract_id), api.obligations(c.contract_id), api.risks(c.contract_id)]);
      })
      .then(([cs, obs, rks]) => {
        setSiblings(cs);
        setObligations(obs);
        setRisks(rks);
      })
      .catch((e) => setError((e as Error).message));
  }, [clauseId]);

  const nav = useMemo(() => {
    if (!clause) return { prev: null as string | null, next: null as string | null };
    const idx = siblings.findIndex((c) => c.clause_id === clause.clause_id);
    return {
      prev: idx > 0 ? siblings[idx - 1].clause_id : null,
      next: idx >= 0 && idx < siblings.length - 1 ? siblings[idx + 1].clause_id : null,
    };
  }, [clause, siblings]);

  if (error) return <div className="wrap"><div className="error">{error}</div></div>;
  if (!clause)
    return (
      <div className="wrap">
        <p className="muted"><span className="spinner" /> Loading clause…</p>
      </div>
    );

  const linkedObligations = obligations.filter((o) => o.source_clause_id === clause.clause_id);
  const linkedRisk = risks.find((r) => r.source_clause_id === clause.clause_id);

  return (
    <div>
      <AppHeader contractId={clause.contract_id} />
      <div className="wrap">
        <Link href={`/contracts/${clause.contract_id}`} style={{ fontSize: 14, fontWeight: 600, color: "var(--muted-2)" }}>
          ← Back to contract
        </Link>

        <div className="grid" style={{ gridTemplateColumns: "1.3fr 0.7fr", gap: 24, marginTop: 16 }}>
          {/* source pane */}
          <div>
            <div className="card">
              <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 14 }}>
                {clause.page ? `Page ${clause.page} · ` : ""}Section {clauseRef(clause.section, clause.clause_id)}
              </div>
              <h2 style={{ fontSize: 20, margin: "0 0 12px" }}>{clause.heading || "Clause"}</h2>
              <div className="wrap-chips" style={{ marginBottom: 16 }}>
                <TypeChip type={clause.clause_type} />
                {clause.is_scanned && <span className="chip chip-rule">scanned → vision OCR</span>}
                {clause.nonstandard && <span className="chip chip-accent">Non-standard clause</span>}
                {clause.nonstandard_similarity != null && (
                  <span className="chip">{Math.round(clause.nonstandard_similarity * 100)}% similar to standard</span>
                )}
              </div>
              <HighlightedText text={clause.text} quote={quote} />
            </div>

            <div className="flex between">
              <button
                className="btn btn-ghost btn-sm"
                disabled={!nav.prev}
                onClick={() => nav.prev && router.push(`/clauses/${nav.prev}`)}
              >
                ← Previous clause
              </button>
              <button
                className="btn btn-ghost btn-sm"
                disabled={!nav.next}
                onClick={() => nav.next && router.push(`/clauses/${nav.next}`)}
              >
                Next clause →
              </button>
            </div>
          </div>

          {/* side panel */}
          <div>
            <div className="card card-tight">
              <h3 style={{ fontFamily: "var(--sans)", fontSize: 14, fontWeight: 700 }}>Linked obligations</h3>
              {linkedObligations.length === 0 ? (
                <div style={{ fontSize: 13, color: "var(--muted)" }}>No obligation tied to this clause.</div>
              ) : (
                linkedObligations.map((o) => (
                  <div key={o.id} style={{ padding: "10px 0", borderTop: "1px solid var(--border)" }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 3 }}>{o.description}</div>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      {typeLabel(o.obligation_type)}
                      {o.obligated_party ? ` · ${o.obligated_party}` : ""} · due {dueLabel(o.due_date, o.obligation_type)}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="card card-tight">
              <h3 style={{ fontFamily: "var(--sans)", fontSize: 14, fontWeight: 700 }}>Risk assessment</h3>
              {linkedRisk ? (
                <>
                  <span
                    className="badge"
                    style={{ color: sevMeta(linkedRisk.severity).color, background: sevMeta(linkedRisk.severity).bg }}
                  >
                    {sevMeta(linkedRisk.severity).label}
                  </span>
                  <div style={{ fontSize: 13.5, fontWeight: 600, margin: "10px 0 6px" }}>{linkedRisk.title}</div>
                  {linkedRisk.rationale && (
                    <div style={{ fontSize: 13, lineHeight: 1.5, color: "var(--muted-2)" }}>{linkedRisk.rationale}</div>
                  )}
                </>
              ) : (
                <div style={{ fontSize: 13, color: "var(--muted)" }}>No risk flagged for this clause.</div>
              )}
            </div>

            {clause.nonstandard && clause.standard_text && (
              <div className="card card-tight">
                <h3 style={{ fontFamily: "var(--sans)", fontSize: 14, fontWeight: 700 }}>Non-standard clause diff</h3>
                {clause.nonstandard_explanation && (
                  <p style={{ fontSize: 13, lineHeight: 1.5, margin: "0 0 12px", color: "var(--muted-2)" }}>
                    {clause.nonstandard_explanation}
                  </p>
                )}
                <SideBySideDiff standard={clause.standard_text} actual={clause.text} title={clause.standard_title} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function ClausePage() {
  return (
    <Suspense fallback={<div className="wrap"><p className="muted">Loading…</p></div>}>
      <ClauseDetail />
    </Suspense>
  );
}
