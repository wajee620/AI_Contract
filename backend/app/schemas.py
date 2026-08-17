"""Shared Pydantic schemas — the API contract between backend tracks and the frontend."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

ObligationType = Literal[
    "payment", "delivery", "reporting", "compliance",
    "data_protection", "renewal", "termination", "other",
]
RiskCategory = Literal["commercial", "legal", "compliance", "delivery", "termination_renewal"]
Severity = Literal["high", "medium", "low"]


class ContractMeta(BaseModel):
    parties: list[str] = Field(default_factory=list)
    effective_date: Optional[str] = None
    term: Optional[str] = None
    renewal_terms: Optional[str] = None
    termination_terms: Optional[str] = None
    governing_law: Optional[str] = None
    total_value: Optional[str] = None


class ClauseOut(BaseModel):
    clause_id: str
    contract_id: str
    section: Optional[str] = None
    heading: Optional[str] = None
    clause_type: str = "other"
    page: Optional[int] = None
    text: str
    is_scanned: bool = False
    nonstandard: bool = False
    nonstandard_similarity: Optional[float] = None
    nonstandard_explanation: Optional[str] = None
    standard_title: Optional[str] = None
    standard_text: Optional[str] = None


class ClauseSummaryOut(BaseModel):
    clause_id: str
    section: Optional[str] = None
    heading: Optional[str] = None
    clause_type: str = "other"
    page: Optional[int] = None
    preview: str = ""
    is_scanned: bool = False
    nonstandard: bool = False
    nonstandard_similarity: Optional[float] = None


class ObligationOut(BaseModel):
    id: str
    contract_id: str
    description: str
    obligated_party: Optional[str] = None
    obligation_type: str = "other"
    due_date: Optional[str] = None
    trigger: Optional[str] = None
    source_clause_id: str
    source_quote: Optional[str] = None


ReviewStatus = Literal["pending", "approved", "dismissed"]


class RiskOut(BaseModel):
    id: str
    contract_id: str
    category: str
    severity: str
    title: str
    rationale: Optional[str] = None
    source_clause_id: str
    source_quote: Optional[str] = None
    flagged_by: Literal["llm", "rule"] = "llm"
    review_status: ReviewStatus = "pending"
    reviewer_note: Optional[str] = None


class ContractOut(BaseModel):
    id: str
    filename: str
    status: str
    progress: Optional[str] = None
    created_at: Optional[datetime] = None
    meta: Optional[ContractMeta] = None
    summary: Optional[str] = None
    num_clauses: int = 0
    num_obligations: int = 0
    num_risks: int = 0
    num_nonstandard: int = 0


class Citation(BaseModel):
    clause_id: str
    section: Optional[str] = None
    heading: Optional[str] = None
    page: Optional[int] = None
    quote: Optional[str] = None


class AskRequest(BaseModel):
    contract_id: str
    question: str
    use_agent: bool = True


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["high", "low"] = "high"
    faithfulness_note: Optional[str] = None
    mode: Literal["agent", "rag"] = "rag"


class IngestResponse(BaseModel):
    contract_id: str
    status: str


# ------------------------------------------------------------- LangGraph agents

# --- Human-in-the-loop risk review (graphs/risk_review.py) ---

class RiskReviewStartResponse(BaseModel):
    """State surfaced when the LangGraph workflow pauses at the human-review interrupt."""
    contract_id: str
    thread_id: str
    status: Literal["awaiting_review", "complete"]
    pending: list[RiskOut] = Field(default_factory=list)
    message: Optional[str] = None


class RiskDecision(BaseModel):
    risk_id: str
    action: Literal["approve", "dismiss", "edit"]
    severity: Optional[Severity] = None          # only for action="edit"
    note: Optional[str] = None


class RiskReviewResumeRequest(BaseModel):
    contract_id: str
    thread_id: str
    decisions: list[RiskDecision] = Field(default_factory=list)


class RiskReviewResult(BaseModel):
    contract_id: str
    status: Literal["complete"]
    approved: int
    dismissed: int
    edited: int
    summary: str


# --- Multi-contract comparison agent (graphs/comparison.py) ---

class CompareRequest(BaseModel):
    contract_ids: list[str] = Field(..., min_length=2)
    question: str = "Compare these contracts on liability, renewal, payment and data protection."


class CompareCitation(BaseModel):
    contract_id: str
    contract_name: Optional[str] = None
    clause_id: str
    section: Optional[str] = None
    quote: Optional[str] = None


class CompareRow(BaseModel):
    dimension: str
    findings: dict[str, str] = Field(default_factory=dict)  # contract_id -> finding text
    assessment: Optional[str] = None                        # which is more favorable + why


class CompareResponse(BaseModel):
    contract_ids: list[str]
    contract_names: dict[str, str] = Field(default_factory=dict)
    dimensions: list[CompareRow] = Field(default_factory=list)
    verdict: str = ""
    citations: list[CompareCitation] = Field(default_factory=list)


# --- Obligation calendar agent (graphs/calendar.py) ---

CalendarBucket = Literal["overdue", "next_30_days", "next_90_days", "later", "recurring", "unscheduled"]


class CalendarEvent(BaseModel):
    obligation_id: str
    contract_id: str
    title: str
    obligated_party: Optional[str] = None
    obligation_type: str = "other"
    raw_due: Optional[str] = None
    resolved_date: Optional[str] = None      # ISO date the agent computed, if any
    bucket: CalendarBucket = "unscheduled"
    urgency: Literal["high", "medium", "low"] = "low"
    note: Optional[str] = None
    source_clause_id: str


class CalendarResponse(BaseModel):
    contract_id: str
    reference_date: str
    events: list[CalendarEvent] = Field(default_factory=list)
    summary: str = ""
