"""Agent A — tool-using Q&A agent.

Decomposes multi-part questions and retrieves iteratively via search_clauses /
get_clause. Guardrails: bounded loop (settings.agent_max_rounds), typed tool
schemas, and graceful fallback to single-shot hybrid RAG on any error — the
agent is an upgrade on a working base, never a single point of failure.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Clause
from app.llm.gateway import chat_raw
from app.schemas import AskResponse
from app.services.answering import (answer_single_shot, build_context,
                                    citations_from_answer, judge_faithfulness)
from app.services.retrieval import retrieve

log = logging.getLogger(__name__)

CLAUSE_TYPES = ["payment", "delivery", "reporting", "compliance", "data_protection",
                "renewal", "termination", "liability", "indemnification",
                "confidentiality", "governing_law", "ip", "definitions", "other"]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_clauses",
            "description": "Hybrid semantic+keyword search over this contract's clauses. "
                           "Returns the top matching clauses with ids and text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Focused search query for one sub-question"},
                    "clause_type": {"type": "string", "enum": CLAUSE_TYPES,
                                    "description": "Optional filter by clause type"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_clause",
            "description": "Fetch the full text of one clause by its id (e.g. to resolve "
                           "'as defined in Section X' references).",
            "parameters": {
                "type": "object",
                "properties": {"clause_id": {"type": "string"}},
                "required": ["clause_id"],
            },
        },
    },
]

AGENT_SYSTEM = """You are a contract analysis agent answering questions about ONE contract.
Break multi-part questions into sub-questions and call search_clauses once per sub-question
(you may issue several tool calls in one turn). Use get_clause when a snippet is cut off or a
clause references another section.
When you have enough evidence, answer using ONLY retrieved clause text. Cite every claim with
the clause id in square brackets, e.g. [ab12cd34-5]. Quote exact figures, dates and notice
periods. If the contract does not address something, say so plainly."""


def _run_tool(db: Session, contract_id: str, name: str, args: dict,
              seen: dict[str, Clause]) -> str:
    if name == "search_clauses":
        clauses = retrieve(db, contract_id, args.get("query", ""),
                           clause_type=args.get("clause_type"), top_n=5)
        for c in clauses:
            seen[c.clause_id] = c
        return json.dumps([
            {"clause_id": c.clause_id, "section": c.section, "heading": c.heading,
             "page": c.page, "text": c.text[:1200]}
            for c in clauses
        ])
    if name == "get_clause":
        c = db.get(Clause, args.get("clause_id", ""))
        if c is None or c.contract_id != contract_id:
            return json.dumps({"error": "clause not found in this contract"})
        seen[c.clause_id] = c
        return json.dumps({"clause_id": c.clause_id, "section": c.section,
                           "heading": c.heading, "page": c.page, "text": c.text})
    return json.dumps({"error": f"unknown tool {name}"})


def answer_with_agent(db: Session, contract_id: str, question: str) -> AskResponse:
    try:
        return _agent_loop(db, contract_id, question)
    except Exception:
        log.exception("Agent failed — falling back to single-shot RAG")
        return answer_single_shot(db, contract_id, question)


def _agent_loop(db: Session, contract_id: str, question: str) -> AskResponse:
    messages: list[dict] = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "user", "content": question},
    ]
    seen: dict[str, Clause] = {}
    answer = ""

    for round_no in range(settings.agent_max_rounds):
        msg = chat_raw(messages, model=settings.extract_model, tools=TOOLS, max_tokens=1200)
        if not msg.tool_calls:
            answer = (msg.content or "").strip()
            break
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(db, contract_id, tc.function.name, args, seen)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    else:
        # Round budget exhausted mid-tool-use: force a final grounded answer.
        messages.append({"role": "user",
                         "content": "Stop searching. Answer now using only the clauses retrieved so far, with [clause_id] citations."})
        answer = chat_raw(messages, model=settings.extract_model, max_tokens=1200).content or ""
        answer = answer.strip()

    if not answer:
        raise RuntimeError("agent produced an empty answer")

    clauses = list(seen.values())
    if not clauses:  # agent never searched — treat as fallback-worthy
        raise RuntimeError("agent answered without retrieving any clauses")

    context = build_context(clauses)
    faithful, note = judge_faithfulness(question, context, answer)
    return AskResponse(
        answer=answer,
        citations=citations_from_answer(answer, clauses),
        confidence="high" if faithful else "low",
        faithfulness_note=note,
        mode="agent",
    )
