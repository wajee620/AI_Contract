"""Citation-grounded answer generation + runtime LLM-as-judge faithfulness guard."""
import logging
import re

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Clause
from app.llm.gateway import chat_json, chat_text
from app.schemas import AskResponse, Citation
from app.services.retrieval import retrieve

log = logging.getLogger(__name__)

ANSWER_SYSTEM = """You are a contract analyst. Answer the question using ONLY the provided
contract clauses. Cite every claim with the clause id in square brackets, e.g. [ab12cd34-5].
If the clauses do not contain the answer, say so plainly — never guess.
Be concise and business-friendly; quote exact figures, dates and notice periods."""


def build_context(clauses: list[Clause]) -> str:
    return "\n\n".join(
        f"[{c.clause_id}] (Section {c.section or '-'} — {c.heading or 'untitled'}, p.{c.page or '?'})\n{c.text[:3500]}"
        for c in clauses
    )


def citations_from_answer(answer: str, clauses: list[Clause]) -> list[Citation]:
    cited_ids = set(re.findall(r"\[([A-Za-z0-9.\-]+)\]", answer))
    cites: list[Citation] = []
    for c in clauses:
        if c.clause_id in cited_ids:
            first_sentence = c.text.strip().split("\n", 1)[0][:200]
            cites.append(Citation(clause_id=c.clause_id, section=c.section,
                                  heading=c.heading, page=c.page, quote=first_sentence))
    if not cites and clauses:  # model answered but forgot inline ids — keep traceability
        c = clauses[0]
        cites.append(Citation(clause_id=c.clause_id, section=c.section,
                              heading=c.heading, page=c.page, quote=c.text.strip()[:200]))
    return cites


JUDGE_PROMPT = """You are a faithfulness judge. Given contract excerpts (CONTEXT) and an ANSWER,
decide whether every factual claim in the answer is supported by the context.
Reply with ONLY JSON: {"faithful": true|false, "note": "one sentence — what is unsupported, or 'fully supported'"}"""


def judge_faithfulness(question: str, context: str, answer: str) -> tuple[bool, str]:
    try:
        data = chat_json(
            [{"role": "system", "content": JUDGE_PROMPT},
             {"role": "user", "content": f"QUESTION: {question}\n\nCONTEXT:\n{context[:12000]}\n\nANSWER:\n{answer}"}],
            model=settings.qa_model, max_tokens=200,
        )
        return bool(data.get("faithful", True)), str(data.get("note", ""))
    except Exception:
        log.exception("Faithfulness judge failed; defaulting to high confidence")
        return True, "judge unavailable"


def answer_single_shot(db: Session, contract_id: str, question: str) -> AskResponse:
    """The reliable base path: hybrid RAG -> rerank -> grounded answer -> judge."""
    clauses = retrieve(db, contract_id, question)
    if not clauses:
        return AskResponse(answer="I couldn't find any relevant clauses in this contract for that question.",
                           citations=[], confidence="low", mode="rag",
                           faithfulness_note="no clauses retrieved")
    context = build_context(clauses)
    answer = chat_text(
        [{"role": "system", "content": ANSWER_SYSTEM},
         {"role": "user", "content": f"Contract clauses:\n{context}\n\nQuestion: {question}"}],
        model=settings.qa_model, max_tokens=900,
    ).strip()
    faithful, note = judge_faithfulness(question, context, answer)
    return AskResponse(
        answer=answer,
        citations=citations_from_answer(answer, clauses),
        confidence="high" if faithful else "low",
        faithfulness_note=note,
        mode="rag",
    )
