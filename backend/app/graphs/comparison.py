"""Multi-contract comparison agent (LangGraph).

Flow:  plan  ->  retrieve  ->  compare  -> END

* plan     — turn the question into comparison dimensions (LLM, with a sensible
             default set of contract dimensions as a fallback).
* retrieve — for every (contract, dimension) pull the most relevant clauses via
             the existing hybrid+rerank retriever, keeping clause_ids for citations.
* compare  — one structured LLM call produces a dimension-by-dimension table + a
             verdict; citations are attached deterministically from the retrieved
             clauses so every finding stays traceable to a source clause.
"""
from __future__ import annotations

import logging
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Clause, Contract
from app.llm.gateway import chat_json
from app.services.retrieval import retrieve

log = logging.getLogger(__name__)

# Fallback dimensions if the planner LLM is unavailable / returns nothing usable.
DEFAULT_PLAN = [
    {"dimension": "Liability", "query": "limitation of liability cap exclusion of damages", "clause_type": "liability"},
    {"dimension": "Term & Renewal", "query": "term duration automatic renewal notice period", "clause_type": "renewal"},
    {"dimension": "Payment", "query": "fees payment terms invoicing late payment interest", "clause_type": "payment"},
    {"dimension": "Data Protection", "query": "personal data processing GDPR data processing agreement", "clause_type": "data_protection"},
    {"dimension": "Termination", "query": "termination rights for cause convenience cure period", "clause_type": "termination"},
]


class CompareState(TypedDict, total=False):
    contract_ids: list[str]
    question: str
    plan: list[dict]
    contract_names: dict
    evidence: dict            # contract_id -> dimension -> [clause dict]
    response: dict


PLAN_PROMPT = """You plan a comparison between contracts. Given the user's question, list the
comparison dimensions. Reply ONLY as JSON: {"dimensions": [{"dimension": "short label",
"query": "retrieval query for that dimension", "clause_type": "one of payment|delivery|reporting|
compliance|data_protection|renewal|termination|liability|indemnification|confidentiality|
governing_law|ip|definitions|other, or null"}]}. 3-6 dimensions. Prefer the standard commercial
dimensions (liability, term/renewal, payment, data protection, termination) unless the question
is narrower."""


def _plan(state: CompareState) -> CompareState:
    names: dict[str, str] = {}
    db = SessionLocal()
    try:
        for cid in state["contract_ids"]:
            c = db.get(Contract, cid)
            names[cid] = (c.filename if c else cid)
    finally:
        db.close()

    plan = DEFAULT_PLAN
    try:
        data = chat_json(
            [{"role": "system", "content": PLAN_PROMPT},
             {"role": "user", "content": state["question"]}],
            model=settings.qa_model, max_tokens=500,
        )
        dims = data.get("dimensions") if isinstance(data, dict) else None
        cleaned = [d for d in (dims or []) if isinstance(d, dict) and d.get("dimension") and d.get("query")]
        if cleaned:
            plan = cleaned[:6]
    except Exception:
        log.exception("Comparison planner failed; using default dimensions")
    return {"plan": plan, "contract_names": names}


def _retrieve(state: CompareState) -> CompareState:
    evidence: dict[str, dict] = {cid: {} for cid in state["contract_ids"]}
    db = SessionLocal()
    try:
        for cid in state["contract_ids"]:
            for step in state["plan"]:
                ctype = step.get("clause_type") or None
                if ctype in (None, "null", ""):
                    ctype = None
                clauses = retrieve(db, cid, step["query"], clause_type=ctype, top_n=2)
                if not clauses:  # retry without the type filter
                    clauses = retrieve(db, cid, step["query"], top_n=2)
                evidence[cid][step["dimension"]] = [
                    {"clause_id": c.clause_id, "section": c.section, "heading": c.heading,
                     "text": c.text[:900]}
                    for c in clauses
                ]
    finally:
        db.close()
    return {"evidence": evidence}


COMPARE_PROMPT = """You compare contracts across the given dimensions using ONLY the provided clauses.
Reply ONLY as JSON: {"dimensions": [{"dimension": str, "findings": {"<contract_id>": "one-sentence
finding for that contract"}, "assessment": "which contract is more favorable on this dimension and
why, one sentence"}], "verdict": "2-3 sentence overall comparison for a business stakeholder"}.
Quote concrete figures, notice periods and caps. If a contract lacks a clause for a dimension, say so."""


def _compare(state: CompareState) -> CompareState:
    names = state.get("contract_names", {})
    evidence = state.get("evidence", {})

    blocks = []
    for cid in state["contract_ids"]:
        blocks.append(f"### CONTRACT {cid} ({names.get(cid, cid)})")
        for step in state["plan"]:
            dim = step["dimension"]
            cls = evidence.get(cid, {}).get(dim, [])
            joined = "\n".join(f"[{c['clause_id']}] (Section {c['section'] or '-'}) {c['text']}" for c in cls) or "(no relevant clause found)"
            blocks.append(f"{dim}:\n{joined}")
    user = (f"Question: {state['question']}\n\nContracts to compare: "
            f"{', '.join(state['contract_ids'])}\n\n" + "\n\n".join(blocks))

    rows: list[dict] = []
    verdict = ""
    try:
        data = chat_json(
            [{"role": "system", "content": COMPARE_PROMPT}, {"role": "user", "content": user}],
            model=settings.extract_model, max_tokens=2500,
        )
        if isinstance(data, dict):
            verdict = str(data.get("verdict", "") or "")
            for d in data.get("dimensions", []) or []:
                if isinstance(d, dict) and d.get("dimension"):
                    rows.append({
                        "dimension": str(d["dimension"]),
                        "findings": {k: str(v) for k, v in (d.get("findings") or {}).items()},
                        "assessment": d.get("assessment"),
                    })
    except Exception:
        log.exception("Comparison LLM call failed")

    if not rows:  # deterministic fallback so the view is never empty
        for step in state["plan"]:
            rows.append({
                "dimension": step["dimension"],
                "findings": {cid: (evidence.get(cid, {}).get(step["dimension"], [{}])[0].get("text", "")[:200]
                                   or "(no relevant clause found)")
                             for cid in state["contract_ids"]},
                "assessment": None,
            })
        verdict = verdict or "Automated comparison unavailable; showing retrieved clauses per dimension."

    # Deterministic citations: top clause per contract per dimension.
    citations = []
    for cid in state["contract_ids"]:
        for step in state["plan"]:
            for c in evidence.get(cid, {}).get(step["dimension"], [])[:1]:
                citations.append({
                    "contract_id": cid, "contract_name": names.get(cid),
                    "clause_id": c["clause_id"], "section": c.get("section"),
                    "quote": (c.get("text") or "")[:220],
                })

    return {"response": {
        "contract_ids": state["contract_ids"],
        "contract_names": names,
        "dimensions": rows,
        "verdict": verdict,
        "citations": citations,
    }}


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        g = StateGraph(CompareState)
        g.add_node("plan", _plan)
        g.add_node("retrieve", _retrieve)
        g.add_node("compare", _compare)
        g.add_edge(START, "plan")
        g.add_edge("plan", "retrieve")
        g.add_edge("retrieve", "compare")
        g.add_edge("compare", END)
        _GRAPH = g.compile()
    return _GRAPH


def compare_contracts(contract_ids: list[str], question: str) -> dict:
    result = _graph().invoke({"contract_ids": contract_ids, "question": question})
    return result.get("response", {}) if isinstance(result, dict) else {}
