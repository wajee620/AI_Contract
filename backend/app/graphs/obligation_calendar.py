"""Obligation calendar agent (LangGraph).

Flow:  load  ->  normalize  ->  prioritize  -> END

Turns free-text obligation deadlines ("within 45 days of invoice", "quarterly",
"2026-09-30") into a prioritized deadline calendar. The LLM resolves relative /
recurring language against the contract's effective date and a reference date;
a deterministic pass then buckets and sorts, and fills in when the LLM is offline.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Contract, Obligation
from app.llm.gateway import chat_json
from app.schemas import ContractMeta

log = logging.getLogger(__name__)

_BUCKET_ORDER = {"overdue": 0, "next_30_days": 1, "next_90_days": 2,
                 "recurring": 3, "later": 4, "unscheduled": 5}
_VALID_BUCKETS = set(_BUCKET_ORDER)
_RECURRING_HINTS = ("month", "quarter", "annual", "year", "weekly", "recurring", "each", "per ")


class CalendarState(TypedDict, total=False):
    contract_id: str
    reference_date: str
    effective_date: str
    obligations: list[dict]
    resolved: dict            # obligation_id -> {resolved_date, bucket, urgency, note}
    events: list[dict]
    summary: str


def _load(state: CalendarState) -> CalendarState:
    db = SessionLocal()
    try:
        rows = db.query(Obligation).filter(Obligation.contract_id == state["contract_id"]).all()
        obligations = [{
            "id": r.id, "description": r.description, "obligated_party": r.obligated_party,
            "obligation_type": r.obligation_type, "due_date": r.due_date, "trigger": r.trigger,
            "source_clause_id": r.source_clause_id,
        } for r in rows]
        eff = ""
        c = db.get(Contract, state["contract_id"])
        if c and c.meta_json:
            try:
                eff = ContractMeta.model_validate(c.meta_json).effective_date or ""
            except Exception:
                eff = ""
        return {"obligations": obligations, "effective_date": eff}
    finally:
        db.close()


NORMALIZE_PROMPT = """You convert contract obligation deadlines into calendar entries.
Given a reference date, the contract effective date, and a list of obligations (each with a
free-text due_date/trigger), reply ONLY as JSON: {"events": [{"obligation_id": str,
"resolved_date": "YYYY-MM-DD or null if it is recurring or has no concrete date",
"bucket": "overdue|next_30_days|next_90_days|later|recurring|unscheduled",
"urgency": "high|medium|low", "note": "short reason, e.g. 'due 45 days after 2026-03-01 invoice'"}]}.
Rules: compute concrete dates relative to the effective/reference dates where possible; mark clearly
periodic obligations (monthly/quarterly/annual) as bucket "recurring"; use "unscheduled" only when no
timing at all is stated. Urgency: high if overdue or within 30 days, medium within 90 days, else low."""


def _normalize(state: CalendarState) -> CalendarState:
    obligations = state.get("obligations", [])
    if not obligations:
        return {"resolved": {}}
    listing = "\n".join(
        f'- id={o["id"]} | type={o["obligation_type"]} | due="{o.get("due_date") or "-"}"'
        f' | trigger="{o.get("trigger") or "-"}" | {o["description"][:160]}'
        for o in obligations
    )
    user = (f"Reference date: {state['reference_date']}\n"
            f"Contract effective date: {state.get('effective_date') or 'unknown'}\n\n"
            f"Obligations:\n{listing}")
    resolved: dict[str, dict] = {}
    try:
        data = chat_json(
            [{"role": "system", "content": NORMALIZE_PROMPT}, {"role": "user", "content": user}],
            model=settings.qa_model, max_tokens=2500,
        )
        for e in (data.get("events", []) if isinstance(data, dict) else []):
            if isinstance(e, dict) and e.get("obligation_id"):
                resolved[str(e["obligation_id"])] = e
    except Exception:
        log.exception("Calendar normalization LLM call failed; using heuristics")
    return {"resolved": resolved}


def _heuristic(o: dict) -> dict:
    """Deterministic fallback bucketing when the LLM did not classify an obligation."""
    due = (o.get("due_date") or "").lower()
    if not due or due in ("-", "none"):
        return {"resolved_date": None, "bucket": "unscheduled", "urgency": "low",
                "note": "No timing stated in the clause."}
    if any(h in due for h in _RECURRING_HINTS):
        return {"resolved_date": None, "bucket": "recurring", "urgency": "medium",
                "note": "Recurring obligation."}
    # A bare ISO date?
    for tok in due.replace(",", " ").split():
        if len(tok) >= 8 and tok[:4].isdigit() and "-" in tok:
            try:
                d = date.fromisoformat(tok[:10])
            except ValueError:
                continue
            ref = date.fromisoformat(_today())
            days = (d - ref).days
            bucket = ("overdue" if days < 0 else "next_30_days" if days <= 30
                      else "next_90_days" if days <= 90 else "later")
            urg = "high" if days <= 30 else "medium" if days <= 90 else "low"
            return {"resolved_date": tok[:10], "bucket": bucket, "urgency": urg,
                    "note": f"Fixed date {tok[:10]}."}
    return {"resolved_date": None, "bucket": "unscheduled", "urgency": "low",
            "note": "Deadline is relative; resolve against a trigger event."}


def _today() -> str:
    return date.today().isoformat()


def _prioritize(state: CalendarState) -> CalendarState:
    resolved = state.get("resolved", {})
    events = []
    for o in state.get("obligations", []):
        r = resolved.get(o["id"]) or _heuristic(o)
        bucket = r.get("bucket") if r.get("bucket") in _VALID_BUCKETS else "unscheduled"
        urg = r.get("urgency") if r.get("urgency") in ("high", "medium", "low") else "low"
        events.append({
            "obligation_id": o["id"], "contract_id": state["contract_id"],
            "title": o["description"][:200], "obligated_party": o.get("obligated_party"),
            "obligation_type": o.get("obligation_type", "other"),
            "raw_due": o.get("due_date"), "resolved_date": r.get("resolved_date"),
            "bucket": bucket, "urgency": urg, "note": r.get("note"),
            "source_clause_id": o["source_clause_id"],
        })
    events.sort(key=lambda e: (_BUCKET_ORDER.get(e["bucket"], 9), e["resolved_date"] or "9999-12-31"))

    counts: dict[str, int] = {}
    for e in events:
        counts[e["bucket"]] = counts.get(e["bucket"], 0) + 1
    parts = [f"{counts[b]} {b.replace('_', ' ')}" for b in _BUCKET_ORDER if counts.get(b)]
    summary = (f"{len(events)} obligation(s): " + ", ".join(parts)) if events else "No obligations found."
    return {"events": events, "summary": summary}


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        g = StateGraph(CalendarState)
        g.add_node("load", _load)
        g.add_node("normalize", _normalize)
        g.add_node("prioritize", _prioritize)
        g.add_edge(START, "load")
        g.add_edge("load", "normalize")
        g.add_edge("normalize", "prioritize")
        g.add_edge("prioritize", END)
        _GRAPH = g.compile()
    return _GRAPH


def build_calendar(contract_id: str, reference_date: str | None = None) -> dict:
    ref = reference_date or _today()
    result = _graph().invoke({"contract_id": contract_id, "reference_date": ref})
    return {
        "contract_id": contract_id,
        "reference_date": ref,
        "events": result.get("events", []) if isinstance(result, dict) else [],
        "summary": result.get("summary", "") if isinstance(result, dict) else "",
    }
