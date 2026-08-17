"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, CompareResponse, Contract } from "@/lib/api";

export default function ComparePage() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState(
    "Compare these contracts on liability, renewal, payment and data protection."
  );
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listContracts()
      .then((cs) => setContracts(cs.filter((c) => c.status === "done")))
      .catch((e) => setError((e as Error).message));
  }, []);

  function toggle(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function run() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.compare(selected, question));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const nameOf = (id: string) =>
    result?.contract_names[id] || contracts.find((c) => c.id === id)?.filename || id;

  const citationsByContract = useMemo(() => {
    const m = new Map<string, CompareResponse["citations"]>();
    (result?.citations || []).forEach((c) => {
      const arr = m.get(c.contract_id) || [];
      arr.push(c);
      m.set(c.contract_id, arr);
    });
    return m;
  }, [result]);

  return (
    <div>
      <div className="appbar">
        <div className="appbar-inner">
          <Link href="/" className="brand">Covenant</Link>
          <div className="nav-pills" />
          <Link href="/contracts" className="btn btn-ghost btn-sm">Upload</Link>
        </div>
      </div>

      <div className="wrap">
        <div className="flex between items-center" style={{ marginBottom: 6 }}>
          <h1 style={{ margin: 0 }}>Compare Contracts</h1>
          <span className="chip chip-accent">Agent · LangGraph</span>
        </div>
        <p className="lead" style={{ marginTop: 6 }}>
          The comparison agent plans the dimensions, retrieves the most relevant clauses from each
          contract (hybrid search + rerank), and produces a side-by-side assessment — every finding
          traceable to a source clause.
        </p>

        {error && <div className="error">{error}</div>}

        <div className="card">
          <div className="eyebrow" style={{ marginBottom: 10 }}>Select two or more contracts</div>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
            {contracts.map((c) => (
              <label
                key={c.id}
                className={`card card-tight ${selected.includes(c.id) ? "selected" : ""}`}
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "center",
                  cursor: "pointer",
                  margin: 0,
                  borderColor: selected.includes(c.id) ? "var(--link)" : undefined,
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.includes(c.id)}
                  onChange={() => toggle(c.id)}
                />
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {c.meta?.parties?.length ? c.meta.parties.join(" ↔ ") : c.filename}
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {c.num_clauses} clauses · {c.num_risks} risks
                  </div>
                </div>
              </label>
            ))}
          </div>
          {contracts.length === 0 && <p className="muted">No processed contracts yet.</p>}

          <input
            className="field"
            style={{ marginTop: 14 }}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What should the comparison focus on?"
          />
          <div className="flex" style={{ marginTop: 12 }}>
            <button className="btn btn-ink" disabled={running || selected.length < 2} onClick={run}>
              {running ? "Comparing…" : `Compare ${selected.length || ""} contracts →`}
            </button>
            {selected.length < 2 && (
              <span className="muted" style={{ fontSize: 12.5, alignSelf: "center", marginLeft: 12 }}>
                Pick at least two.
              </span>
            )}
          </div>
        </div>

        {result && (
          <>
            {result.verdict && (
              <div className="card" style={{ borderLeft: "3px solid var(--link)" }}>
                <div className="eyebrow" style={{ marginBottom: 8 }}>Verdict</div>
                <p style={{ fontSize: 14.5, lineHeight: 1.6, margin: 0 }}>{result.verdict}</p>
              </div>
            )}

            <div className="card" style={{ overflowX: "auto" }}>
              <table className="cmp-table">
                <thead>
                  <tr>
                    <th style={{ textAlign: "left" }}>Dimension</th>
                    {result.contract_ids.map((cid) => (
                      <th key={cid} style={{ textAlign: "left" }}>{nameOf(cid)}</th>
                    ))}
                    <th style={{ textAlign: "left" }}>Assessment</th>
                  </tr>
                </thead>
                <tbody>
                  {result.dimensions.map((row) => (
                    <tr key={row.dimension}>
                      <td style={{ fontWeight: 700 }}>{row.dimension}</td>
                      {result.contract_ids.map((cid) => (
                        <td key={cid} style={{ fontSize: 13, lineHeight: 1.5, verticalAlign: "top" }}>
                          {row.findings[cid] || <span className="muted">—</span>}
                        </td>
                      ))}
                      <td style={{ fontSize: 13, lineHeight: 1.5, color: "var(--muted-2)", verticalAlign: "top" }}>
                        {row.assessment || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card">
              <div className="eyebrow" style={{ marginBottom: 12 }}>Source clauses</div>
              {result.contract_ids.map((cid) => (
                <div key={cid} style={{ marginBottom: 14 }}>
                  <div style={{ fontWeight: 700, fontSize: 13.5, marginBottom: 6 }}>{nameOf(cid)}</div>
                  {(citationsByContract.get(cid) || []).map((c) => (
                    <Link
                      key={c.clause_id}
                      href={`/clauses/${c.clause_id}?q=${encodeURIComponent(c.quote || "")}`}
                      className="card card-tight"
                      style={{ display: "block", margin: "0 0 8px" }}
                    >
                      <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", marginBottom: 4 }}>
                        §{c.section || c.clause_id} →
                      </div>
                      <div style={{ fontSize: 12.5, color: "var(--muted-2)", lineHeight: 1.5 }}>
                        {c.quote}
                      </div>
                    </Link>
                  ))}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
