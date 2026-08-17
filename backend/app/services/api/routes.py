from __future__ import annotations
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import uploads_dir
from app.db.database import SessionLocal
from app.db.models import Clause, Contract, Obligation, Risk
from app.graphs import comparison, obligation_calendar, risk_review
from app.schemas import (AskRequest, AskResponse, CalendarResponse, ClauseOut,
                         ClauseSummaryOut, CompareRequest, CompareResponse,
                         ContractMeta, ContractOut, IngestResponse, ObligationOut,
                         RiskOut, RiskReviewResult, RiskReviewResumeRequest,
                         RiskReviewStartResponse)
from app.services.agent import answer_with_agent
from app.services.answering import answer_single_shot
from app.services.pipeline import run_ingestion

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
def health():
    from app.config import settings
    return {"status": "ok", "mock_llm": settings.mock_llm}


@router.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile, background_tasks: BackgroundTasks,
                 db: Session = Depends(get_db)):
    ext = Path(file.filename or "upload").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Use PDF, DOCX, TXT or MD.")
    contract_id = uuid.uuid4().hex[:16]
    dest = uploads_dir() / f"{contract_id}{ext}"
    dest.write_bytes(await file.read())

    db.add(Contract(id=contract_id, filename=file.filename or dest.name,
                    status="queued", progress="Waiting to start"))
    db.commit()
    background_tasks.add_task(run_ingestion, contract_id, str(dest))
    return IngestResponse(contract_id=contract_id, status="queued")


def _contract_out(db: Session, c: Contract) -> ContractOut:
    meta = None
    if c.meta_json:
        try:
            meta = ContractMeta.model_validate(c.meta_json)
        except Exception:
            meta = None
    return ContractOut(
        id=c.id, filename=c.filename, status=c.status, progress=c.progress,
        created_at=c.created_at, meta=meta, summary=c.summary,
        num_clauses=db.query(Clause).filter(Clause.contract_id == c.id).count(),
        num_obligations=db.query(Obligation).filter(Obligation.contract_id == c.id).count(),
        num_risks=db.query(Risk).filter(Risk.contract_id == c.id).count(),
        num_nonstandard=db.query(Clause).filter(Clause.contract_id == c.id,
                                                Clause.nonstandard.is_(True)).count(),
    )


@router.get("/contracts", response_model=list[ContractOut])
def list_contracts(db: Session = Depends(get_db)):
    contracts = db.query(Contract).order_by(Contract.created_at.desc()).all()
    return [_contract_out(db, c) for c in contracts]


@router.get("/contracts/{contract_id}", response_model=ContractOut)
def get_contract(contract_id: str, db: Session = Depends(get_db)):
    c = db.get(Contract, contract_id)
    if c is None:
        raise HTTPException(404, "Contract not found")
    return _contract_out(db, c)


@router.get("/contracts/{contract_id}/obligations", response_model=list[ObligationOut])
def list_obligations(contract_id: str, db: Session = Depends(get_db)):
    rows = db.query(Obligation).filter(Obligation.contract_id == contract_id).all()
    return [ObligationOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/contracts/{contract_id}/risks", response_model=list[RiskOut])
def list_risks(contract_id: str, status: str | None = None, db: Session = Depends(get_db)):
    """status filter: 'pending' | 'approved' | 'dismissed' | 'active'
    ('active' = approved + pending, i.e. everything not dismissed)."""
    q = db.query(Risk).filter(Risk.contract_id == contract_id)
    if status == "active":
        q = q.filter(Risk.review_status != "dismissed")
    elif status:
        q = q.filter(Risk.review_status == status)
    rows = q.all()
    order = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda r: order.get(r.severity, 3))
    return [RiskOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/contracts/{contract_id}/clauses", response_model=list[ClauseSummaryOut])
def list_clauses(contract_id: str, db: Session = Depends(get_db)):
    rows = (db.query(Clause).filter(Clause.contract_id == contract_id)
            .order_by(Clause.chunk_index).all())
    return [
        ClauseSummaryOut(
            clause_id=r.clause_id, section=r.section, heading=r.heading,
            clause_type=r.clause_type, page=r.page, preview=r.text[:220],
            is_scanned=r.is_scanned, nonstandard=r.nonstandard,
            nonstandard_similarity=r.nonstandard_similarity,
        )
        for r in rows
    ]


@router.get("/clauses/{clause_id}", response_model=ClauseOut)
def get_clause(clause_id: str, db: Session = Depends(get_db)):
    c = db.get(Clause, clause_id)
    if c is None:
        raise HTTPException(404, "Clause not found")
    return ClauseOut.model_validate(c, from_attributes=True)


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, db: Session = Depends(get_db)):
    contract = db.get(Contract, req.contract_id)
    if contract is None:
        raise HTTPException(404, "Contract not found")
    if contract.status != "done":
        raise HTTPException(409, f"Contract is still processing (status: {contract.status})")
    if req.use_agent:
        return answer_with_agent(db, req.contract_id, req.question)
    return answer_single_shot(db, req.contract_id, req.question)


# ----------------------------------------------------------- LangGraph agents

def _require_done(db: Session, contract_id: str) -> Contract:
    c = db.get(Contract, contract_id)
    if c is None:
        raise HTTPException(404, "Contract not found")
    if c.status != "done":
        raise HTTPException(409, f"Contract is still processing (status: {c.status})")
    return c


@router.post("/contracts/{contract_id}/risk-review/start", response_model=RiskReviewStartResponse)
def risk_review_start(contract_id: str, db: Session = Depends(get_db)):
    """Human-in-the-loop: run the LangGraph risk-review graph until it pauses at
    the review interrupt. Returns the pending risks + a thread_id to resume with."""
    _require_done(db, contract_id)
    thread_id = f"risk-review:{contract_id}:{uuid.uuid4().hex[:8]}"
    state = risk_review.start_review(contract_id, thread_id)
    return RiskReviewStartResponse(
        contract_id=contract_id, thread_id=thread_id, status=state["status"],
        pending=[RiskOut.model_validate(p) for p in state.get("pending", [])],
        message=state.get("message"),
    )


@router.post("/contracts/{contract_id}/risk-review/resume", response_model=RiskReviewResult)
def risk_review_resume(contract_id: str, req: RiskReviewResumeRequest,
                       db: Session = Depends(get_db)):
    """Resume the paused graph with the human's approve/dismiss/edit decisions."""
    _require_done(db, contract_id)
    decisions = [d.model_dump() for d in req.decisions]
    res = risk_review.resume_review(req.thread_id, decisions)
    if not res:
        raise HTTPException(409, "No paused review found for this thread_id (start one first).")
    return RiskReviewResult(
        contract_id=contract_id, status="complete",
        approved=res.get("approved", 0), dismissed=res.get("dismissed", 0),
        edited=res.get("edited", 0), summary=res.get("summary", ""),
    )


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest, db: Session = Depends(get_db)):
    """Multi-contract comparison agent (LangGraph plan -> retrieve -> compare)."""
    for cid in req.contract_ids:
        _require_done(db, cid)
    result = comparison.compare_contracts(req.contract_ids, req.question)
    return CompareResponse.model_validate(result)


@router.get("/contracts/{contract_id}/calendar", response_model=CalendarResponse)
def calendar(contract_id: str, reference_date: str | None = None,
             db: Session = Depends(get_db)):
    """Obligation calendar agent: normalize + prioritize obligation deadlines."""
    _require_done(db, contract_id)
    result = obligation_calendar.build_calendar(contract_id, reference_date)
    return CalendarResponse.model_validate(result)
