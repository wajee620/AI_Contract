"""Human-in-the-loop risk-approval workflow (LangGraph).

Flow:  load_pending  ->  [interrupt: human decides]  ->  apply_decisions  -> END

The graph pauses at a real LangGraph `interrupt()`; its state is persisted by a
checkpointer so the pause can span two separate HTTP requests (start / resume).
This is where LangGraph earns its place — the same pattern is painful to hand-roll.

The gateway is only used for an optional natural-language wrap-up of the human's
decisions, so the workflow runs fully offline (MOCK_LLM=1) too.
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Risk
from app.llm.gateway import chat_text
from app.schemas import RiskOut

log = logging.getLogger(__name__)


class ReviewState(TypedDict, total=False):
    contract_id: str
    pending: list[dict]          # snapshot presented to the human
    result: dict                 # counts + summary once applied


def _load_pending(state: ReviewState) -> ReviewState:
    db = SessionLocal()
    try:
        rows = (db.query(Risk)
                .filter(Risk.contract_id == state["contract_id"],
                        Risk.review_status == "pending")
                .all())
        order = {"high": 0, "medium": 1, "low": 2}
        rows.sort(key=lambda r: order.get(r.severity, 3))
        pending = [RiskOut.model_validate(r, from_attributes=True).model_dump() for r in rows]
        return {"pending": pending}
    finally:
        db.close()


def _human_review(state: ReviewState) -> ReviewState:
    """Pause for the human. Resumes with a list of decision dicts (RiskDecision)."""
    pending = state.get("pending", [])
    if not pending:
        return {"result": {"approved": 0, "dismissed": 0, "edited": 0,
                           "summary": "No pending risks to review."}}

    # First run raises GraphInterrupt and persists here; on resume, `interrupt`
    # returns the decisions passed via Command(resume=...).
    decisions: list[dict] = interrupt({
        "kind": "risk_review",
        "contract_id": state["contract_id"],
        "pending": pending,
        "message": f"{len(pending)} risk(s) awaiting human approval.",
    })
    return _apply(state["contract_id"], pending, decisions or [])


def _apply(contract_id: str, pending: list[dict], decisions: list[dict]) -> ReviewState:
    by_id = {d.get("risk_id"): d for d in decisions}
    approved = dismissed = edited = 0
    db = SessionLocal()
    try:
        for risk in pending:
            d = by_id.get(risk["id"])
            action = (d or {}).get("action", "approve")   # default: keep the risk
            row = db.get(Risk, risk["id"])
            if row is None:
                continue
            note = (d or {}).get("note")
            if action == "dismiss":
                row.review_status = "dismissed"
                dismissed += 1
            elif action == "edit":
                new_sev = (d or {}).get("severity")
                if new_sev:
                    row.severity = new_sev
                row.review_status = "approved"
                edited += 1
                approved += 1
            else:  # approve
                row.review_status = "approved"
                approved += 1
            if note:
                row.reviewer_note = note
        db.commit()
    finally:
        db.close()

    summary = _summarize(contract_id, approved, dismissed, edited)
    return {"result": {"approved": approved, "dismissed": dismissed,
                       "edited": edited, "summary": summary}}


def _summarize(contract_id: str, approved: int, dismissed: int, edited: int) -> str:
    base = (f"Human review complete: {approved} approved "
            f"({edited} with edited severity), {dismissed} dismissed.")
    try:
        return chat_text(
            [{"role": "system", "content": "You summarize a contract risk-review decision in one short sentence for an audit log."},
             {"role": "user", "content": base}],
            model=settings.qa_model, max_tokens=80,
        ).strip() or base
    except Exception:
        log.exception("Review summary LLM call failed; using template")
        return base


# --------------------------------------------------------------- graph assembly

_CHECKPOINTER = MemorySaver()  # process-lifetime; persists interrupts across requests
_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        g = StateGraph(ReviewState)
        g.add_node("load_pending", _load_pending)
        g.add_node("human_review", _human_review)
        g.add_edge(START, "load_pending")
        g.add_edge("load_pending", "human_review")
        g.add_edge("human_review", END)
        _GRAPH = g.compile(checkpointer=_CHECKPOINTER)
    return _GRAPH


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _interrupt_payload(result: dict) -> dict | None:
    """Extract the interrupt value regardless of minor version return shape."""
    intr = result.get("__interrupt__") if isinstance(result, dict) else None
    if intr:
        first = intr[0]
        return getattr(first, "value", first)
    return None


def start_review(contract_id: str, thread_id: str) -> dict:
    """Run until the human-review interrupt. Returns awaiting_review or complete."""
    graph = _graph()
    result = graph.invoke({"contract_id": contract_id}, config=_config(thread_id))
    payload = _interrupt_payload(result)
    if payload is not None:
        return {"status": "awaiting_review",
                "pending": payload.get("pending", []),
                "message": payload.get("message")}
    # No interrupt fired -> nothing pending, graph ran to completion.
    res = result.get("result", {}) if isinstance(result, dict) else {}
    return {"status": "complete", "pending": [], "message": res.get("summary")}


def resume_review(thread_id: str, decisions: list[dict]) -> dict:
    """Resume the paused graph with the human's decisions and apply them."""
    graph = _graph()
    result = graph.invoke(Command(resume=decisions), config=_config(thread_id))
    return result.get("result", {}) if isinstance(result, dict) else {}
