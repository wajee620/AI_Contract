"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, Contract } from "@/lib/api";
import { StatusChip } from "@/components/ui";

// Maps the backend's ingestion statuses onto a human-readable step checklist.
const ORDER = ["queued", "parsing", "chunking", "indexing", "extracting", "analyzing", "summarizing", "done"];
const STEPS = [
  { key: "parsing", label: "Reading document & detecting text layers" },
  { key: "chunking", label: "Clause-aware chunking" },
  { key: "indexing", label: "Embedding & indexing clauses" },
  { key: "extracting", label: "Extracting obligations, dates & owners" },
  { key: "analyzing", label: "Assessing risk & non-standard clauses" },
  { key: "summarizing", label: "Writing business summary" },
  { key: "done", label: "Contract ready for review" },
];
const DONE_RANK = ORDER.indexOf("done");

export default function UploadPage() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setContracts(await api.listContracts());
      setError(null);
    } catch (e) {
      setError(`Backend unreachable: ${(e as Error).message}`);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, [refresh]);

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const { contract_id } = await api.ingest(file);
        setActiveId(contract_id);
        await refresh();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setUploading(false);
      }
    },
    [refresh]
  );

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  }

  const active = contracts.find((c) => c.id === activeId) || null;
  const statusRank = active ? ORDER.indexOf(active.status) : -1;

  return (
    <div>
      <div className="appbar">
        <div className="appbar-inner">
          <Link href="/" className="brand">Covenant</Link>
          <div className="nav-pills" />
          <div className="flex items-center gap-12">
            <Link href="/compare" className="btn btn-ghost btn-sm">Compare contracts</Link>
            <Link href="/" className="btn btn-ghost btn-sm">← Home</Link>
          </div>
        </div>
      </div>

      <div className="wrap">
        <h1>Upload &amp; Ingest</h1>
        <p className="lead">
          Native-text pages are parsed directly; scanned pages fall back to vision-model OCR.
          Every clause gets a stable ID for traceability downstream.
        </p>

        {error && <div className="error">{error}</div>}

        <div className="grid" style={{ gridTemplateColumns: "1.1fr 0.9fr", gap: 24 }}>
          {/* upload column */}
          <div>
            <div
              className={`dropzone ${dragging ? "drag" : ""}`}
              style={{ marginBottom: 20 }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>Drag a contract here, or browse</div>
              <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 20 }}>
                PDF, DOCX, TXT — including scanned / image-only PDFs
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.txt,.md"
                style={{ display: "none" }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) upload(f);
                  e.target.value = "";
                }}
              />
              <button className="btn" disabled={uploading} onClick={() => fileRef.current?.click()}>
                {uploading ? "Uploading…" : "Browse files"}
              </button>
            </div>

            {active && (
              <div className="card">
                <div className="flex between items-center" style={{ marginBottom: 4 }}>
                  <strong style={{ fontSize: 14 }}>{active.filename}</strong>
                  <StatusChip status={active.status} progress={active.progress} />
                </div>
                <div className="progress-track" style={{ marginTop: 14 }}>
                  <div
                    className="progress-fill"
                    style={{ width: `${Math.max(6, Math.round((Math.max(statusRank, 0) / DONE_RANK) * 100))}%` }}
                  />
                </div>

                {active.status === "failed" ? (
                  <div className="error mb-0">Ingestion failed: {active.progress}</div>
                ) : (
                  STEPS.map((step) => {
                    const rank = ORDER.indexOf(step.key);
                    const done = statusRank > rank || active.status === "done";
                    const isActive = statusRank === rank && active.status !== "done";
                    const icon = done ? "✓" : isActive ? "●" : "○";
                    const color = done ? "var(--sev-low)" : isActive ? "var(--link)" : "oklch(75% 0.01 258)";
                    return (
                      <div className="step-row" key={step.key}>
                        <span style={{ color, width: 16 }}>{icon}</span>
                        <span style={{ color: done || isActive ? "var(--text)" : "var(--muted)" }}>
                          {isActive && active.progress ? active.progress : step.label}
                        </span>
                      </div>
                    );
                  })
                )}

                {active.status === "done" && (
                  <Link href={`/contracts/${active.id}`} className="btn btn-ink btn-sm" style={{ marginTop: 14 }}>
                    View contract overview →
                  </Link>
                )}
              </div>
            )}
          </div>

          {/* recently ingested column */}
          <div>
            <div className="eyebrow" style={{ marginBottom: 12 }}>Recently ingested</div>
            {contracts.length === 0 ? (
              <p className="muted">Nothing here yet — upload a contract to get started.</p>
            ) : (
              contracts.map((c) => (
                <Link key={c.id} href={`/contracts/${c.id}`} className="card card-tight" style={{ display: "block" }}>
                  <div className="flex between items-center">
                    <strong style={{ fontSize: 14 }}>{c.filename}</strong>
                    <StatusChip status={c.status} progress={c.progress} />
                  </div>
                  <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 4 }}>
                    {c.num_clauses} clauses · {c.num_obligations} obligations · {c.num_risks} risks
                    {c.num_nonstandard > 0 ? ` · ${c.num_nonstandard} non-standard` : ""}
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
