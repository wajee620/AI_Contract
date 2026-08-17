"""Retrieval: hybrid dense + BM25 with RRF fusion, then LLM rerank top-20 -> top-5."""
from __future__ import annotations
import logging
import re

from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Clause
from app.llm.gateway import chat_json, embed
from app.services.vectorstore import get_store

log = logging.getLogger(__name__)

RRF_K = 60
HYBRID_TOP_K = 20
FINAL_TOP_K = 5


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _bm25_rank(clauses: list[Clause], query: str, top_k: int) -> list[str]:
    if not clauses:
        return []
    corpus = [_tokenize(c.text) for c in clauses]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(clauses, scores), key=lambda x: -x[1])
    return [c.clause_id for c, s in ranked[:top_k] if s > 0]


def hybrid_search(db: Session, contract_id: str, query: str,
                  clause_type: str | None = None, top_k: int = HYBRID_TOP_K) -> list[Clause]:
    """Dense (vector store) + BM25 (Postgres/SQLite corpus) fused with RRF."""
    q = db.query(Clause).filter(Clause.contract_id == contract_id)
    if clause_type:
        q = q.filter(Clause.clause_type == clause_type)
    clauses = q.all()
    if not clauses:
        return []

    dense_ids: list[str] = []
    try:
        qvec = embed([query])[0]
        hits = get_store().search(qvec, contract_id, top_k=top_k, clause_type=clause_type)
        dense_ids = [h[0].get("clause_id") for h in hits if h[0].get("clause_id")]
    except Exception:
        log.exception("Dense search failed; continuing with BM25 only")

    sparse_ids = _bm25_rank(clauses, query, top_k)

    scores: dict[str, float] = {}
    for ranking in (dense_ids, sparse_ids):
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)

    fused = sorted(scores, key=lambda cid: -scores[cid])[:top_k]
    by_id = {c.clause_id: c for c in clauses}
    return [by_id[cid] for cid in fused if cid in by_id]


RERANK_PROMPT = """You rerank contract clauses by relevance to a question.
Reply with ONLY JSON: {"ranking": ["clause_id", ...]} â€” the ids of the most relevant
clauses first, at most %d ids, only ids from the provided list."""


def rerank(query: str, clauses: list[Clause], top_n: int = FINAL_TOP_K) -> list[Clause]:
    if len(clauses) <= top_n:
        return clauses
    listing = "\n\n".join(
        f"[{c.clause_id}] (Section {c.section or '-'} â€” {c.heading or 'untitled'})\n{c.text[:500]}"
        for c in clauses
    )
    by_id = {c.clause_id: c for c in clauses}
    try:
        data = chat_json(
            [{"role": "system", "content": RERANK_PROMPT % top_n},
             {"role": "user", "content": f"Question: {query}\n\nClauses:\n{listing}"}],
            model=settings.qa_model, max_tokens=400,
        )
        ranked = [by_id[cid] for cid in data.get("ranking", []) if cid in by_id]
    except Exception:
        log.exception("Rerank failed; using RRF order")
        ranked = []
    for c in clauses:  # top up with fused order if the model returned too few
        if len(ranked) >= top_n:
            break
        if c not in ranked:
            ranked.append(c)
    return ranked[:top_n]


def retrieve(db: Session, contract_id: str, query: str,
             clause_type: str | None = None, top_n: int = FINAL_TOP_K) -> list[Clause]:
    candidates = hybrid_search(db, contract_id, query, clause_type=clause_type)
    return rerank(query, candidates, top_n=top_n)
