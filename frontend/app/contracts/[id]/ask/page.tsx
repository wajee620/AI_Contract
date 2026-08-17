"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";
import { api, AskResponse, Citation } from "@/lib/api";
import { clauseRef } from "@/lib/format";

interface Msg {
  role: "user" | "ai";
  text: string;
  loading?: boolean;
  error?: string;
  resp?: AskResponse;
}

const PRESETS = [
  "When does this contract renew, and how do we stop it?",
  "What's our liability exposure if there's a data breach?",
  "Is there anything non-standard compared to our usual contracts?",
];

/** Turn inline [clause_id] citations in the answer into §-links (or drop unknown ones). */
function AnswerText({ resp }: { resp: AskResponse }) {
  const sectionOf = new Map(resp.citations.map((c) => [c.clause_id, c] as const));
  const parts = resp.answer.split(/\[([A-Za-z0-9.\-]+)\]/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>;
        const c = sectionOf.get(part);
        if (!c) return null; // unknown id — drop the raw token
        return (
          <Link key={i} href={clauseLink(c)} style={{ fontWeight: 700 }}>
            §{clauseRef(c.section, c.clause_id)}
          </Link>
        );
      })}
    </span>
  );
}

function clauseLink(c: Citation) {
  return `/clauses/${c.clause_id}?q=${encodeURIComponent(c.quote || "")}`;
}

export default function AskPage() {
  const { id } = useParams<{ id: string }>();
  const [thread, setThread] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [useAgent, setUseAgent] = useState(true);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thread]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true);
    setInput("");
    setThread((t) => [...t, { role: "user", text: q }, { role: "ai", text: "", loading: true }]);
    try {
      const resp = await api.ask(id, q, useAgent);
      setThread((t) => replaceLast(t, { role: "ai", text: resp.answer, resp }));
    } catch (e) {
      setThread((t) => replaceLast(t, { role: "ai", text: "", error: (e as Error).message }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Ask Covenant</h1>
      <p className="lead">
        Ask questions about this contract — every answer cites the exact clause it came from.
      </p>

      <div className="grid" style={{ gridTemplateColumns: "230px 1fr", gap: 20 }}>
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>Try asking</div>
          {PRESETS.map((p) => (
            <button key={p} className="preset-btn" disabled={busy} onClick={() => ask(p)}>
              {p}
            </button>
          ))}
        </div>

        <div>
          <div className="chat-panel">
            {thread.length === 0 && (
              <p className="muted" style={{ margin: "auto", textAlign: "center" }}>
                Ask a question, or pick one on the left. Answers are grounded in this contract&apos;s clauses.
              </p>
            )}
            {thread.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                {m.loading ? (
                  <div className="bubble">
                    <span className="spinner" /> Retrieving clauses and drafting a grounded answer…
                  </div>
                ) : m.error ? (
                  <div className="bubble" style={{ color: "var(--sev-high)" }}>{m.error}</div>
                ) : (
                  <div className="bubble">{m.resp ? <AnswerText resp={m.resp} /> : m.text}</div>
                )}

                {m.resp && m.resp.citations.length > 0 && (
                  <div className="wrap-chips" style={{ marginTop: 6 }}>
                    {m.resp.citations.map((c) => (
                      <Link key={c.clause_id} href={clauseLink(c)} className="cite-link" title={c.heading || undefined}>
                        §{clauseRef(c.section, c.clause_id)}
                      </Link>
                    ))}
                  </div>
                )}

                {m.resp && (
                  <div className="flex items-center" style={{ gap: 8, marginTop: 6 }}>
                    <span
                      className="badge"
                      title={m.resp.faithfulness_note || undefined}
                      style={
                        m.resp.confidence === "high"
                          ? { color: "var(--sev-low)", background: "var(--sev-low-bg)" }
                          : { color: "var(--sev-high)", background: "var(--sev-high-bg)" }
                      }
                    >
                      {m.resp.confidence === "high" ? "Verified" : "Low confidence — verify source"}
                    </span>
                    <span style={{ fontSize: 11.5, color: "var(--muted)" }}>
                      {m.resp.mode === "agent" ? "agentic" : "single-shot RAG"}
                    </span>
                  </div>
                )}
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <div className="flex" style={{ gap: 10 }}>
            <input
              className="field"
              style={{ flex: 1 }}
              value={input}
              placeholder="Ask a question about this contract…"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  ask(input);
                }
              }}
            />
            <button className="btn btn-ink" disabled={busy || !input.trim()} onClick={() => ask(input)}>
              Send
            </button>
          </div>
          <label className="flex items-center" style={{ gap: 6, marginTop: 10, fontSize: 12.5, color: "var(--muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={useAgent} onChange={(e) => setUseAgent(e.target.checked)} />
            Agentic mode — decomposes multi-part questions, falls back to single-shot RAG on error
          </label>
        </div>
      </div>
    </main>
  );
}

function replaceLast(thread: Msg[], msg: Msg): Msg[] {
  const copy = [...thread];
  copy[copy.length - 1] = msg;
  return copy;
}
