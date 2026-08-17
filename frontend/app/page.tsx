import Link from "next/link";

const HOW_STEPS = [
  { n: 1, title: "Ingest & OCR", text: "Native-text pages parse directly; scanned pages fall back to vision-model OCR, structure preserved." },
  { n: 2, title: "Extract & structure", text: "Obligations, dates, owners, and contract metadata are pulled into a structured, queryable record." },
  { n: 3, title: "Assess risk", text: "Clauses are checked against a standard library and a risk rubric to flag high-risk, non-standard terms." },
  { n: 4, title: "Ask & verify", text: "Ask follow-up questions and get cited answers, with a confidence flag when the system is unsure." },
];

const FEATURES = [
  { title: "Obligation tracker", text: "Every due date, owner, and commitment in one sortable, filterable view." },
  { title: "Risk detection", text: "Commercial, legal, compliance, and delivery risks surfaced with plain-English rationale." },
  { title: "Traceable citations", text: "Every extracted fact and answer links back to the exact source clause." },
  { title: "Non-standard clause diff", text: "See exactly how a clause deviates from your standard template, side by side." },
  { title: "Renewal timeline", text: "Never miss a renewal or termination notice window again." },
  { title: "Faithfulness guard", text: "Low-confidence answers are flagged for human review instead of stated as fact." },
];

const RAI_POINTS = [
  "All processing runs locally — contracts never leave your environment.",
  "This demo uses anonymized, synthetic contract data only.",
  "Every extracted fact and answer cites its source clause for verification.",
  'Low-confidence answers are flagged "verify source" rather than stated as fact.',
];

export default function LandingPage() {
  return (
    <div className="wrap-narrow">
      {/* nav */}
      <div className="flex between items-center" style={{ padding: "26px 0" }}>
        <div className="flex items-center" style={{ gap: 10, alignItems: "baseline" }}>
          <span className="brand" style={{ fontSize: 22 }}>Covenant</span>
          <span style={{ fontSize: 12, color: "var(--muted)", letterSpacing: "0.04em" }}>
            Contract Intelligence
          </span>
        </div>
        <div className="flex items-center" style={{ gap: 28 }}>
          <a href="#how" style={{ fontSize: 14, fontWeight: 600, color: "var(--muted-2)" }}>How it works</a>
          <a href="#security" style={{ fontSize: 14, fontWeight: 600, color: "var(--muted-2)" }}>Security</a>
          <Link href="/contracts" className="btn">Open live demo</Link>
        </div>
      </div>

      {/* hero */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.05fr 0.95fr",
          gap: 56,
          alignItems: "center",
          padding: "72px 0 88px",
        }}
      >
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.08em", color: "var(--link)", marginBottom: 18 }}>
            AI CONTRACT INTELLIGENCE
          </div>
          <h1 style={{ fontSize: 52, lineHeight: 1.1, margin: "0 0 24px" }}>
            Know every obligation.<br />Catch every risk.<br />Before it&apos;s a problem.
          </h1>
          <p style={{ fontSize: 17, lineHeight: 1.6, color: "var(--muted-2)", maxWidth: 480, margin: "0 0 32px" }}>
            Covenant reads your contracts, statements of work, and amendments — then surfaces
            obligations, deadlines, and risks with a citation back to the exact clause, every time.
          </p>
          <div className="flex" style={{ gap: 14 }}>
            <Link href="/contracts" className="btn btn-lg">Open live demo</Link>
            <a href="#how" className="btn btn-ghost btn-lg">See how it works</a>
          </div>
        </div>
        <div className="card" style={{ padding: 28, marginBottom: 0 }}>
          <div
            className="flex items-center"
            style={{ gap: 10, background: "var(--sev-high-bg)", borderRadius: 10, padding: "14px 16px", marginBottom: 14 }}
          >
            <span className="dot" style={{ background: "var(--sev-high)" }} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>Narrow 30-day auto-renewal notice window</span>
          </div>
          <div style={{ textAlign: "center", color: "var(--muted)", fontSize: 20, margin: "6px 0" }}>↓</div>
          <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10, padding: 16 }}>
            <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>Page 4 · Section 2.3 · Term and Renewal</div>
            <div style={{ fontSize: 14, lineHeight: 1.55 }}>
              This Agreement shall renew automatically for successive twelve (12) month terms unless
              either Party provides written notice of non-renewal at least <mark>thirty (30) days</mark>{" "}
              prior to the end of the then-current term.
            </div>
          </div>
        </div>
      </div>

      {/* audience strip */}
      <div
        className="flex"
        style={{ justifyContent: "center", gap: 56, padding: "22px 0", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}
      >
        {["LEGAL", "PROCUREMENT", "DELIVERY", "COMPLIANCE"].map((t) => (
          <span key={t} className="eyebrow">{t}</span>
        ))}
      </div>

      {/* how it works */}
      <div id="how" style={{ padding: "88px 0" }}>
        <h2 style={{ fontSize: 30, textAlign: "center", margin: "0 0 44px" }}>From raw contract to answered question</h2>
        <div className="grid" style={{ gridTemplateColumns: "repeat(4,1fr)", gap: 32 }}>
          {HOW_STEPS.map((s) => (
            <div key={s.n}>
              <div
                className="flex items-center"
                style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--accent)", color: "var(--ink)", justifyContent: "center", fontWeight: 700, marginBottom: 16 }}
              >
                {s.n}
              </div>
              <h3 style={{ fontSize: 18 }}>{s.title}</h3>
              <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--muted-2)", margin: 0 }}>{s.text}</p>
            </div>
          ))}
        </div>
      </div>

      {/* features */}
      <div style={{ padding: "0 0 88px" }}>
        <h2 style={{ fontSize: 30, textAlign: "center", margin: "0 0 8px" }}>Everything your team needs to stay ahead</h2>
        <p style={{ textAlign: "center", color: "var(--muted-2)", margin: "0 0 44px" }}>
          Built for procurement, legal, and delivery teams managing live contracts.
        </p>
        <div className="grid" style={{ gridTemplateColumns: "repeat(3,1fr)", gap: 20 }}>
          {FEATURES.map((f) => (
            <div key={f.title} className="card" style={{ marginBottom: 0 }}>
              <h3 style={{ fontFamily: "var(--sans)", fontSize: 16, fontWeight: 700 }}>{f.title}</h3>
              <p style={{ fontSize: 14, lineHeight: 1.55, color: "var(--muted-2)", margin: 0 }}>{f.text}</p>
            </div>
          ))}
        </div>
      </div>

      {/* responsible AI */}
      <div id="security" style={{ padding: "0 0 88px" }}>
        <div className="card" style={{ padding: 44, marginBottom: 0 }}>
          <h2 style={{ fontSize: 26, margin: "0 0 24px" }}>Built with responsible AI in mind</h2>
          <div className="grid" style={{ gridTemplateColumns: "repeat(2,1fr)", gap: "18px 40px" }}>
            {RAI_POINTS.map((p) => (
              <div key={p} className="flex" style={{ gap: 10, fontSize: 14, lineHeight: 1.5, color: "var(--muted-2)" }}>
                <span style={{ color: "var(--link)", flexShrink: 0 }}>—</span>
                <span>{p}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CTA */}
      <div style={{ textAlign: "center", padding: "0 0 72px" }}>
        <h2 style={{ fontSize: 28, margin: "0 0 24px" }}>See it on your own contracts</h2>
        <Link href="/contracts" className="btn btn-lg">Open live demo</Link>
      </div>

      <div style={{ borderTop: "1px solid var(--border)", padding: "24px 0", textAlign: "center", fontSize: 13, color: "var(--muted)" }}>
        Covenant — synthetic demo data. Not for use with real client or vendor information.
      </div>
    </div>
  );
}
