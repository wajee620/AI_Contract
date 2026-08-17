"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, Risk, RiskDecision, RiskReviewResult } from "@/lib/api";
import { categoryLabel, clauseRef } from "@/lib/format";
import { SeverityBadge } from "@/components/ui";

type Action = "approve" | "dismiss";
interface Draft {
  action: Action;
  severity: "high" | "medium" | "low";
  note: string;
}

const SEVERITIES: Array<"high" | "medium" | "low"> = ["high", "medium", "low"];

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [pending, setPending] = useState<Risk[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<RiskReviewResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const s = await api.riskReviewStart(id);
      setThreadId(s.thread_id);
      setPending(s.pending);
      setMessage(s.message ?? null);
      const d: Record<string, Draft> = {};
      s.pending.forEach((r) => {
        d[r.id] = { action: "approve", severity: normSev(r.severity), note: "" };
      });
      setDrafts(d);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    start();
  }, [start]);

  function patch(riskId: string, p: Partial<Draft>) {
    setDrafts((prev) => ({ ...prev, [riskId]: { ...prev[riskId], ...p } }));
  }

  async function submit() {
    if (!threadId) return;
    setSubmitting(true);
    setError(null);
    try {
      const decisions: RiskDecision[] = pending.map((r) => {
        const d = drafts[r.id];
        if (d.action === "dismiss")
          return { risk_id: r.id, action: "dismiss", note: d.note || null };
        if (d.severity !== normSev(r.severity))
          return { risk_id: r.id, action: "edit", severity: d.severity, note: d.note || null };
        return { risk_id: r.id, action: "approve", note: d.note || null };
      });
      const res = await api.riskReviewResume(id, threadId, decisions);
      setResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const counts = summarize(pending, drafts);

  return (
    <main>
      <div className="flex between items-center" style={{ marginBottom: 6 }}>
        <h1 style={{ margin: 0 }}>Risk Review</h1>
        <span className="chip chip-accent">Human-in-the-loop · LangGraph</span>
      </div>
      <p className="lead" style={{ marginTop: 6 }}>
        The extraction agent proposes risks; a reviewer approves, re-grades, or dismisses each one
        before it becomes an active finding. The workflow pauses at a LangGraph{" "}
        <code>interrupt()</code> and resumes with your decisions.
      </p>

      {error && <div className="error">{error}</div>}

      {loading && <p className="muted">Starting review workflow…</p>}

      {!loading && result && (
        <div className="card" style={{ borderLeft: "3px solid var(--sev-low)" }}>
          <h3 style={{ marginTop: 0 }}>Review committed ✓</h3>
          <p style={{ fontSize: 14, lineHeight: 1.55 }}>{result.summary}</p>
          <div className="flex" style={{ gap: 16, marginTop: 8 }}>
            <Stat n={result.approved} label="approved" color="var(--sev-low)" />
            <Stat n={result.edited} label="re-graded" color="var(--sev-med)" />
            <Stat n={result.dismissed} label="dismissed" color="var(--muted)" />
          </div>
          <div className="flex" style={{ gap: 10, marginTop: 16 }}>
            <Link href={`/contracts/${id}/risks`} className="btn btn-ink btn-sm">
              View active risks →
            </Link>
            <button className="btn btn-ghost btn-sm" onClick={start}>
              Run another review
            </button>
          </div>
        </div>
      )}

      {!loading && !result && pending.length === 0 && (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            {message || "No pending risks awaiting review — all risks have already been triaged."}
          </p>
          <Link href={`/contracts/${id}/risks`} className="btn btn-ghost btn-sm" style={{ marginTop: 12 }}>
            View risks →
          </Link>
        </div>
      )}

      {!loading && !result && pending.length > 0 && (
        <>
          <div className="flex between items-center" style={{ margin: "18px 0 14px" }}>
            <span className="muted" style={{ fontSize: 13 }}>
              {pending.length} risk(s) awaiting decision · {counts.approve} keep · {counts.edit} re-grade ·{" "}
              {counts.dismiss} dismiss
            </span>
            <button className="btn btn-ink" disabled={submitting} onClick={submit}>
              {submitting ? "Committing…" : "Commit review →"}
            </button>
          </div>

          {pending.map((r) => {
            const d = drafts[r.id];
            if (!d) return null;
            const dismissed = d.action === "dismiss";
            return (
              <div
                key={r.id}
                className="card"
                style={{ opacity: dismissed ? 0.6 : 1, transition: "opacity .15s" }}
              >
                <div className="flex between items-center" style={{ marginBottom: 10 }}>
                  <SeverityBadge severity={r.severity} />
                  <span style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)" }}>
                    {categoryLabel(r.category)}
                    {r.flagged_by === "rule" ? " · rule" : ""}
                  </span>
                </div>
                <h3 style={{ fontSize: 17, margin: "0 0 8px" }}>{r.title}</h3>
                {r.rationale && (
                  <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--muted-2)", margin: "0 0 14px" }}>
                    {r.rationale}
                  </p>
                )}

                <div className="flex items-center" style={{ gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                  <button
                    className={`chip-round ${!dismissed ? "chip-active" : "chip"}`}
                    onClick={() => patch(r.id, { action: "approve" })}
                  >
                    Keep
                  </button>
                  <button
                    className={`chip-round ${dismissed ? "chip-active" : "chip"}`}
                    onClick={() => patch(r.id, { action: "dismiss" })}
                  >
                    Dismiss
                  </button>
                  <span style={{ fontSize: 13, color: "var(--muted)", marginLeft: 6 }}>Severity</span>
                  <select
                    className="field"
                    style={{ width: "auto" }}
                    value={d.severity}
                    disabled={dismissed}
                    onChange={(e) => patch(r.id, { severity: e.target.value as Draft["severity"] })}
                  >
                    {SEVERITIES.map((s) => (
                      <option key={s} value={s}>
                        {s[0].toUpperCase() + s.slice(1)}
                        {s !== normSev(r.severity) ? " (re-grade)" : ""}
                      </option>
                    ))}
                  </select>
                </div>

                <input
                  className="field"
                  placeholder="Reviewer note (optional, saved to the audit trail)"
                  value={d.note}
                  onChange={(e) => patch(r.id, { note: e.target.value })}
                  style={{ marginBottom: 12 }}
                />

                <div className="flex between items-center">
                  <span />
                  <Link
                    href={`/clauses/${r.source_clause_id}?q=${encodeURIComponent(r.source_quote || "")}`}
                    style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}
                  >
                    View source clause §{clauseRef(null, r.source_clause_id)} →
                  </Link>
                </div>
              </div>
            );
          })}

          <div className="flex" style={{ justifyContent: "flex-end", marginTop: 8 }}>
            <button className="btn btn-ink" disabled={submitting} onClick={submit}>
              {submitting ? "Committing…" : "Commit review →"}
            </button>
          </div>
        </>
      )}
    </main>
  );
}

function normSev(s: string): "high" | "medium" | "low" {
  return s === "med" ? "medium" : (s as "high" | "medium" | "low");
}

function summarize(pending: Risk[], drafts: Record<string, Draft>) {
  let approve = 0,
    edit = 0,
    dismiss = 0;
  pending.forEach((r) => {
    const d = drafts[r.id];
    if (!d) return;
    if (d.action === "dismiss") dismiss++;
    else if (d.severity !== normSev(r.severity)) edit++;
    else approve++;
  });
  return { approve, edit, dismiss };
}

function Stat({ n, label, color }: { n: number; label: string; color: string }) {
  return (
    <div className="flex items-center" style={{ gap: 6, fontSize: 14, fontWeight: 600 }}>
      <span style={{ color, fontSize: 18 }}>{n}</span>
      <span className="muted">{label}</span>
    </div>
  );
}
