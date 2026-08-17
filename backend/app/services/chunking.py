"""Clause-aware chunking: one clause = one chunk.

Splits on section numbering / headings (numbered or ALL-CAPS), carries page
numbers through, and falls back to fixed-size splitting only for oversized
sections. This is the traceability spine â€” clause_id links Postgres, Qdrant,
obligations, risks, and the UI click-through.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from app.services.parsing import PageText

MAX_CLAUSE_CHARS = 6000   # beyond this a section gets split
SPLIT_TARGET_CHARS = 3000

# "3. Term", "Section 4.2 Fees and Payment", "10) Limitation of Liability"
NUMBERED_HEADING = re.compile(
    r"^\s*(?:(?:Section|SECTION|Article|ARTICLE|Clause|CLAUSE)\s+)?"
    r"(\d{1,2}(?:\.\d{1,2}){0,2})[.):]?\s+(\S.{2,90})\s*$"
)
# "LIMITATION OF LIABILITY"
CAPS_HEADING = re.compile(r"^\s*([A-Z][A-Z0-9 &/,'\-]{5,70})\s*$")


@dataclass
class RawChunk:
    section: str | None
    heading: str | None
    page: int
    is_scanned: bool = False
    lines: list[str] = field(default_factory=list)
    text: str = ""


# Ordered: first match on heading wins, then body keywords.
HEADING_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("termination", ["termination", "terminate"]),
    ("renewal", ["renewal", "renew", "term and renewal", "initial term", "term of agreement", "term"]),
    ("payment", ["payment", "fees", "fee", "pricing", "price", "invoic", "charges", "compensation"]),
    ("liability", ["limitation of liability", "liability", "liabilities"]),
    ("indemnification", ["indemn"]),
    ("data_protection", ["data protection", "personal data", "privacy", "data processing", "gdpr", "data security"]),
    ("confidentiality", ["confidential", "non-disclosure"]),
    ("delivery", ["service level", "sla", "deliverable", "delivery", "milestone", "scope of services", "scope of work", "services"]),
    ("reporting", ["report", "audit"]),
    ("compliance", ["compliance", "anti-corruption", "anti-bribery", "sanctions", "regulatory", "applicable law"]),
    ("governing_law", ["governing law", "jurisdiction", "dispute", "arbitration"]),
    ("ip", ["intellectual property", "license", "ownership"]),
    ("definitions", ["definitions", "interpretation"]),
]

BODY_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("data_protection", ["personal data", "data protection", "gdpr"]),
    ("liability", ["limitation of liability", "liable for", "liability"]),
    ("renewal", ["automatically renew", "renewal term"]),
    ("termination", ["terminate this agreement"]),
    ("payment", ["invoice", "payable within"]),
    ("governing_law", ["governed by the laws"]),
    ("confidentiality", ["confidential information"]),
]


def classify_clause_type(heading: str | None, text: str) -> str:
    h = (heading or "").lower()
    # Document titles ("Master Services Agreement") are preamble, not typed clauses â€”
    # keeps them out of type filters and the non-standard comparison.
    if h and re.search(r"\bagreement\b", h) and not any(
            k in h for k in ("term", "renewal", "data processing", "termination")):
        return "other"
    if h:
        for ctype, keys in HEADING_TYPE_RULES:
            if any(k in h for k in keys):
                return ctype
    body = text[:600].lower()
    for ctype, keys in BODY_TYPE_RULES:
        if any(k in body for k in keys):
            return ctype
    return "other"


def _is_heading(line: str) -> tuple[str | None, str | None] | None:
    """Return (section, heading) if this line opens a new clause, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 95:
        return None
    m = NUMBERED_HEADING.match(stripped)
    if m:
        title = m.group(2).strip()
        # A real heading title starts with an uppercase letter â€” this rejects
        # ordinary sentences that happen to start with a number ("12 months ...").
        if title[:1].isupper() and len(title.split()) <= 12 and not title.endswith((",", ";")):
            return m.group(1), title
    c = CAPS_HEADING.match(stripped)
    if c and not stripped.isdigit() and len(stripped.split()) <= 8:
        return None, c.group(1).strip().title()
    return None


def split_into_clauses(pages: list[PageText]) -> list[RawChunk]:
    chunks: list[RawChunk] = []
    current: RawChunk | None = None

    def close() -> None:
        nonlocal current
        if current is not None:
            current.text = "\n".join(current.lines).strip()
            if current.text:
                chunks.append(current)
        current = None

    for pg in pages:
        for line in pg.text.splitlines():
            hit = _is_heading(line)
            if hit is not None:
                close()
                current = RawChunk(section=hit[0], heading=hit[1], page=pg.page, is_scanned=pg.is_scanned)
                current.lines.append(line.strip())
            else:
                if current is None:
                    current = RawChunk(section=None, heading=None, page=pg.page, is_scanned=pg.is_scanned)
                current.lines.append(line)
                current.is_scanned = current.is_scanned or pg.is_scanned
    close()

    return _split_oversized(chunks)


def _split_oversized(chunks: list[RawChunk]) -> list[RawChunk]:
    out: list[RawChunk] = []
    for ch in chunks:
        if len(ch.text) <= MAX_CLAUSE_CHARS:
            out.append(ch)
            continue
        paras = re.split(r"\n\s*\n", ch.text)
        buf, part = "", 0
        for para in paras:
            if buf and len(buf) + len(para) > SPLIT_TARGET_CHARS:
                out.append(RawChunk(section=ch.section, heading=ch.heading, page=ch.page,
                                    is_scanned=ch.is_scanned, text=buf.strip()))
                part += 1
                buf = para
            else:
                buf = f"{buf}\n\n{para}" if buf else para
        if buf.strip():
            out.append(RawChunk(section=ch.section, heading=ch.heading, page=ch.page,
                                is_scanned=ch.is_scanned, text=buf.strip()))
    return out


def make_clause_id(contract_id: str, chunk: RawChunk, index: int, used: set[str]) -> str:
    prefix = contract_id.split("-")[0][:8]
    base = chunk.section if chunk.section else f"s{index + 1}"
    base = re.sub(r"[^A-Za-z0-9.]", "", base)
    cid = f"{prefix}-{base}"
    suffix_ord = 0
    candidate = cid
    while candidate in used:
        suffix_ord += 1
        candidate = f"{cid}{chr(ord('a') + (suffix_ord - 1) % 26)}"
    used.add(candidate)
    return candidate
