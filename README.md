# ClauseTrace — AI Contract Obligation & Risk Review

A working prototype that ingests contracts (PDF/DOCX/TXT, including **scanned PDFs via vision-LLM OCR**), extracts obligations, key terms and risks, flags non-standard clauses, and answers questions — with **every finding traceable to the exact source clause** (click any risk/obligation/citation → highlighted clause text).

Built per the locked design in [task.md](task.md): RAG substrate + agentic layer + faithfulness guard.

## Quickstart

### 0. Secrets
Copy `.env.example` → `.env` and set a **valid** gateway key:

```
api_endpoint=""
api_key="sk-..."
```

> ⚠️ The previously shared key was revoked (gateway returns `token_not_found_in_db`). Rotate/obtain a fresh key before the demo. `.env` is git-ignored — never commit it.

### Option A — docker-compose (demo laptop)
```
docker-compose up --build
```
Brings up Qdrant (6333) + Postgres (5432) + FastAPI backend (8000) + Next.js frontend (3000). Open http://localhost:3000.

### Option B — no Docker (lite mode)
The backend auto-falls back to **SQLite + a local vector index** when `DATABASE_URL`/Qdrant aren't available — full functionality, zero infra.

```
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --port 8000   # use 8010 if 8000 is taken

cd ..\frontend
npm install
npm run dev            # set NEXT_PUBLIC_API_URL if the backend isn't on :8000
```

### Demo prep
```
cd backend
python scripts\make_pdfs.py                       # PDFs + image-only "scanned" variant
python scripts\seed.py --api http://localhost:8000            # pre-ingest contracts 01+02
python scripts\seed.py --include-scanned ...                  # also the scanned one (slow, OCR)
python scripts\run_eval.py --api http://localhost:8000 ^
    --contract-id <id1> --contract-file 01_msa_orion_helix ^
    --contract-id <id2> --contract-file 02_saas_nova_atlas    # THE eval number
```

## Architecture map (code ↔ design)

| Design element | Code |
|---|---|
| Gateway client (chat / embed / vision OCR / JSON mode) | `backend/app/llm/gateway.py` |
| Text-layer detection + vision-LLM OCR | `backend/app/services/parsing.py` |
| Clause-aware chunking + clause_id spine + type tagging | `backend/app/services/chunking.py` |
| Qdrant (primary) / local fallback vector store | `backend/app/services/vectorstore.py` |
| Obligations / ContractMeta / risks (LLM + 3 override rules) / summary | `backend/app/services/extraction.py` |
| Hybrid dense+BM25 → RRF → LLM rerank 20→5 | `backend/app/services/retrieval.py` |
| Grounded answer + runtime faithfulness judge ("low confidence" flag) | `backend/app/services/answering.py` |
| Agent A (bounded tool loop, fallback to single-shot RAG) | `backend/app/services/agent.py` |
| Non-standard detection (similarity vs standard library + LLM diff explanation) | `backend/app/services/nonstandard.py` |
| Ingestion orchestrator with status polling | `backend/app/services/pipeline.py` |
| REST API (`/ingest`, `/contracts…`, `/clauses/{id}`, `/ask`) | `backend/app/api/routes.py` |
| Six UI views + click-through highlight + side-by-side diff | `frontend/app/**` |
| Synthetic contracts / standard-clause library / gold Q&A | `data/**` |
| Offline eval harness (retrieval hit-rate + faithfulness %) | `backend/scripts/run_eval.py` |

**Traceability spine:** `clause_id` links Qdrant payloads ↔ SQL rows ↔ obligations/risks ↔ UI deep links (`/clauses/{clause_id}?q=<quote>` highlights the cited passage).

**Model routing** (override via env): embeddings `text-embedding-3-large` · extraction+agent `gpt-4.1` · Q&A/rerank/judge `gpt-4.1-mini` · OCR `gpt-4o` (the design's Llama-3.2-90B-Vision was retired by the gateway; gpt-4o won the replacement bake-off — see `scripts/check_models.py`).

**Synthetic data:** contract 01 (Orion/Helix MSA) deliberately trips all three override rules — unlimited liability, 15-day auto-renewal notice, personal data without DPA; contract 02 (Nova/Atlas SaaS) is the clean comparison. `03_…scanned.pdf` is image-only for the OCR demo.

## Offline mock mode (no gateway key needed)
Set `MOCK_LLM=1` to run the entire stack with deterministic dummy LLM outputs (`backend/app/llm/mock.py`): embeddings become hashing-vectorizer vectors (retrieval/BM25/RRF/similarity all behave realistically), chat calls return schema-valid `[MOCK]`-tagged replies. Useful for pipeline tests, frontend work, and dev machines without credentials. The deterministic risk rules, chunking, storage, and API are the real code paths — only model calls are stubbed.

## Notes
- Corporate TLS interception is handled via `truststore` (uses the OS certificate store).
- No auth/multi-tenancy by design: local-only processing, synthetic data, secrets in env.
- Agent B (cross-reference resolution at extraction time) is deliberately not built yet — it is first in the agreed cut order; contract 01 §12/§14 contain "as defined in Section …" hooks for it.
