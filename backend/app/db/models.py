from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[str | None] = mapped_column(String(512), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)


class Clause(Base):
    __tablename__ = "clauses"

    clause_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(64), index=True)
    section: Mapped[str | None] = mapped_column(String(32), nullable=True)
    heading: Mapped[str | None] = mapped_column(String(256), nullable=True)
    clause_type: Mapped[str] = mapped_column(String(64), default="other")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    is_scanned: Mapped[bool] = mapped_column(Boolean, default=False)
    nonstandard: Mapped[bool] = mapped_column(Boolean, default=False)
    nonstandard_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    nonstandard_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    standard_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class Obligation(Base):
    __tablename__ = "obligations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text)
    obligated_party: Mapped[str | None] = mapped_column(String(256), nullable=True)
    obligation_type: Mapped[str] = mapped_column(String(32), default="other")
    due_date: Mapped[str | None] = mapped_column(String(256), nullable=True)
    trigger: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_clause_id: Mapped[str] = mapped_column(String(128))
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    contract_id: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(256))
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_clause_id: Mapped[str] = mapped_column(String(128))
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    flagged_by: Mapped[str] = mapped_column(String(16), default="llm")
    # Human-in-the-loop review gate (LangGraph risk-review workflow):
    # pending -> approved | dismissed. reviewer_note captures any human comment.
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
