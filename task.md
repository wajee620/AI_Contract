# Context Handoff — AI-Powered Contract Obligation & Risk Review Assistant

> Paste this into a new Claude session to continue with full context. This captures a completed design/"grilling" session for a hackathon project. All decisions below are LOCKED unless noted.

## Project brief
An AI contract-intelligence assistant that ingests contracts (PDF/DOCX, incl. scanned), extracts obligations/due-dates/owners/service-commitments/data-protection requirements, identifies commercial/legal/compliance/delivery risks, flags non-standard/high-risk clauses, generates business-friendly summaries + an obligation tracker, and answers questions — all with **traceable citations back to the exact source clause**. Data is synthetic + anonymized. Responsible-AI framing required.

## Constraints
- **Deliverable:** real working prototype (not a mockup).
- **Team:** 5 people. **Time:** 2 days (hackathon).
- **Judging goal:** live functionality + traceability; "architectural depth that works in the demo," not box-diagrams.

## Models —  GenAI Lab gateway (OpenAI-compatible)
- Endpoint (base_url): `` — call with the **OpenAI SDK**, `base_url` set here. Models support function/tool calling.
- **API key must be rotated + kept in env only (it was exposed in chat). Never commit.**
- Embeddings: `azure/genailab-maas-text-embedding-3-large` (3072-dim)
- Extraction + agents: `azure/genailab-maas-gpt-4.1`
- Q&A generation + rerank + faithfulness-judge: `azure/genailab-maas-gpt-4.1-mini`
- OCR (vision): `azure_ai/genailab-maas-Llama-3.2-90B-Vision-Instruct`
- (NOT using Anthropic/Claude API — the earlier part of the session assumed Claude before the gateway was revealed.)

## Architecture — LOCKED decisions

### Pattern
- **RAG-based** (chosen over long-context). Pre-extract everything at ingest into Postgres; RAG powers interactive Q&A + citation grounding.

### Storage — split, joined by shared `clause_id`
- **Qdrant** (vectors + sparse/BM25 + payload/metadata filtering)
- **Postgres** (structured obligations + contract meta)
- Deliberate separation-of-concerns; one owner on the sync path. Fall back to Postgres+pgvector only if sync fights us.

### Ingestion pipeline (one adaptive pipeline)
- Per-page **text-layer detection**: native-text pages extracted directly (pdfplumber/PyMuPDF); scanned pages rendered to image → **vision-LLM OCR** (Llama-3.2-90B-Vision), structure-preserving.
- **Clause-aware chunking** (split on section numbering/headings; one clause = one chunk; fixed-size fallback for oversized sections).
- Metadata per chunk: `contract_id`, `clause_id`, `clause_type`, `section`, `page`.

### Extraction (pre-computed at ingest; structured outputs / JSON schema)
- `Obligation` (per clause): id, description, obligated_party, obligation_type (payment|delivery|reporting|compliance|data_protection|renewal|termination|other), due_date, trigger, source_clause_id, source_quote, risk link.
- `ContractMeta` (per doc): parties, effective_date, term, renewal_terms, termination_terms, governing_law, total_value.

### Risk (hybrid: LLM-first + thin rule layer)
- LLM emits: category (commercial|legal|compliance|delivery|termination_renewal), severity (high|med|low), rationale, source_clause_id — anchored to an in-prompt rubric with examples.
- 3–5 deterministic override rules for always-flag patterns (unlimited liability, short-notice auto-renewal, missing DPA).

### Non-standard clause detection
- Small **synthetic standard-clause library** → embed each extracted clause → nearest standard clause of same type → below similarity threshold = flag non-standard → single LLM call explains deviation → **side-by-side diff** in UI.

### RAG pipeline (the engineered core) — mapped to the 4 canonical stages
1. **Ingestion:** clause-aware chunking + rich metadata (above).
2. **Indexing:** text-embedding-3-large → Qdrant (dense + BM25) keyed by clause_id; Postgres for structured, joined on clause_id.
3. **Retrieval:** query rewriting/decomposition (via Agent A) → **hybrid dense+BM25 with RRF fusion** + metadata filtering → **rerank top-20→top-5** (gpt-4.1-mini).
4. **Generation + evaluation:** context assembly (top-5 clauses + metadata) → gpt-4.1-mini citation-grounded answer → click-through to highlighted clause → **evaluation (committed): offline harness (15–20 gold Q&A → retrieval hit-rate + faithfulness %) + runtime LLM-as-judge faithfulness guard ("low confidence, verify source" flag).**

### Agentic layer — A + B (both committed)
- **Agent A — tool-using Q&A agent:** decomposes multi-part questions, iterative retrieval via `search_clauses(query, filter)` / `get_clause(clause_id)`. Reliability guardrails: bounded loop (max ~3 rounds), typed tool schemas, **graceful fallback to single-shot hybrid RAG** if it errors/caps out. It's an upgrade on a working base, never a single point of failure.
- **Agent B — cross-reference resolution in extraction:** on "as defined in Section X," calls `get_clause(X)` before finalizing an obligation. Higher-value, higher-risk; owned by whoever finishes core first.
- Rejected: multi-agent orchestrator as the spine (demo-fragile).

### Frontend / backend
- **Next.js (React) + FastAPI.** Six views: (1) Upload/ingest w/ progress, (2) Contract overview + summary + top risks, (3) Obligation tracker (sortable/filterable + renewal timeline), (4) Risk view, (5) Clause detail / source pane (highlighted text + page image + non-standard diff), (6) Ask (agentic Q&A).
- **Hero interaction:** click any risk/obligation → jump to highlighted source clause.

### Ops
- **docker-compose local** (Qdrant + Postgres + FastAPI + Next.js). No auth/multi-tenancy.
- Pre-ingest 2–3 anonymized synthetic contracts (incl. one scanned, for OCR) + do one **live upload** in the demo.
- "Secure handling" = local-only processing + anonymized data + env-secret talking points (not built auth).

## Golden-path demo (~3 min)
Live upload → watch it process → overview + risk headline → tracker filtered to "renewal, next 90 days" → click high-risk auto-renewal → highlighted source clause → flagged non-standard w/ side-by-side diff → one cited agentic Q&A follow-up.

## Failure-point audit (the 4 to avoid)
1. Chunks for speed not meaning → AVOIDED (clause-aware chunking).
2. Metadata skipped → AVOIDED (clause_id is the traceability spine; non-negotiable).
3. Retrieval volume not relevance → AVOIDED (hybrid + RRF + rerank + metadata filter).
4. No evaluation → AVOIDED **only because eval is promoted to committed** (offline harness + runtime faithfulness guard).

## Plan of action

### Phase 0 — shared foundation (~3 hrs, whole team, blocks everything)
1. Repo + docker-compose skeleton (Qdrant+Postgres+FastAPI+Next.js boot with one command; env file for gateway key).
2. Gateway client wrapper: `chat(model, messages, tools?)`, `embed(texts)`, `vision_ocr(image)`.
3. Shared Pydantic schemas: Chunk(+metadata), Obligation, ContractMeta, Risk.
4. API contract stubbed with fake data: `POST /ingest`, `GET /contracts/{id}`, `GET /contracts/{id}/obligations`, `GET /contracts/{id}/risks`, `GET /clauses/{clause_id}`, `POST /ask`.
5. 2–3 synthetic anonymized contracts (incl. one scanned).
- Exit: everyone can `docker-compose up`, call gateway, see schemas + stubbed endpoints.

### Day 1 — vertical slice (5 parallel tracks)
- **Backend-1:** ingestion + clause-aware chunking + metadata → Qdrant+Postgres; then **extraction** (Obligation/ContractMeta/risk, structured outputs).
- **Backend-2:** retrieval (hybrid dense+BM25+RRF) + rerank + citation-grounded single-shot answer.
- **OCR/Library-1:** text-layer detection → vision-LLM OCR → same chunk output; seed synthetic standard-clause library.
- **Frontend-1:** upload flow + contract overview + obligation tracker.
- **Frontend-2:** risk view + **clause detail pane with click-through highlight (hero interaction).**
- **Day 1 milestone (non-negotiable): walking skeleton** — upload native-text contract → chunked/extracted/indexed → obligations+risks in UI → click → source clause → single-shot RAG Q&A works. No agent/OCR-polish/eval yet.

### Day 2 — upgrade, harden, rehearse
- AM: Agent A (Q&A, bounded + fallback); Agent B (cross-ref, by whoever's free); non-standard detection + diff; live OCR upload; frontend (renewal timeline, page-image pane, diff view, Ask screen).
- Midday: **evaluation** (offline harness + runtime faithfulness guard).
- PM: **feature freeze ~4 hrs before demo**; pre-ingest contracts; rehearse golden path 3× on the real demo laptop/network; prep credibility lines (eval number + "RAG substrate + agentic layer + faithfulness guard").

### Standing rules
- Integration checkpoints: end of Phase 0, midday Day 1, end of Day 1 (skeleton gate), midday Day 2.
- **Cut order if slipping (protect left→right):** Agent B → page-image OCR pane → renewal timeline (fold into tracker column) → non-standard LLM explanation (keep similarity flag, drop generated explanation).
- **Never cut:** clause-aware chunking, metadata, traceability click-through, the eval number.
- Demo laptop is sacred; everything runs via docker-compose, tested on real network before judging.

## Open items to confirm at start
1. Eval committed (recommended yes) — assumed committed here.
2. 5 owners mapped to actual team strengths (esp. React comfort + who takes agents).
3. Rotate the exposed gateway API key.

## Status
Design/grilling complete. Not yet started building. Next step: Phase 0.
