"""Pre-computed extraction at ingest: ContractMeta, Obligations, Risks, summary.

LLM-first (structured JSON outputs, gpt-4.1) with a thin deterministic rule
layer for always-flag patterns (unlimited liability, short-notice auto-renewal,
missing DPA). Every item is anchored to a source_clause_id + verbatim quote.
"""
from __future__ import annotations
import logging
import re
import uuid

from app.config import settings
from app.db.models import Clause
from app.llm.gateway import chat_json, chat_text
from app.schemas import ContractMeta

log = logging.getLogger(__name__)

OBLIGATION_TYPES = ["payment", "delivery", "reporting", "compliance",
                    "data_protection", "renewal", "termination", "other"]
RISK_CATEGORIES = ["commercial", "legal", "compliance", "delivery", "termination_renewal"]
SEVERITIES = ["high", "medium", "low"]

CLAUSE_BATCH_SIZE = 8


def _clause_block(clauses: list[Clause]) -> str:
    parts = []
    for c in clauses:
        head = f"[{c.clause_id}] (Section {c.section or '-'} â€” {c.heading or 'untitled'})"
        parts.append(f"{head}\n{c.text[:4000]}")
    return "\n\n".join(parts)


def _resolve_clause_id(raw: str | None, clauses: list[Clause], by_id: dict[str, Clause]) -> str | None:
    """LLMs occasionally cite a bare section number instead of the exact id."""
    if not raw:
        return None
    raw = raw.strip()
    if raw in by_id:
        return raw
    for c in clauses:
        if c.section and (raw == c.section or raw.endswith(f"-{c.section}")):
            return c.clause_id
    return None


# ---------------------------------------------------------------- contract meta

META_PROMPT = """You extract contract metadata. Reply with ONLY a JSON object:
{"parties": [list of party legal names], "effective_date": str|null, "term": str|null,
 "renewal_terms": str|null, "termination_terms": str|null, "governing_law": str|null,
 "total_value": str|null}
Use concise values copied or lightly paraphrased from the contract. null when absent."""


def extract_contract_meta(full_text: str) -> ContractMeta:
    data = chat_json(
        [{"role": "system", "content": META_PROMPT},
         {"role": "user", "content": full_text[:24000]}],
        model=settings.extract_model,
    )
    try:
        return ContractMeta.model_validate(data)
    except Exception:
        log.exception("Meta validation failed; returning empty meta")
        return ContractMeta()


# ---------------------------------------------------------------- obligations

OBLIGATIONS_PROMPT = f"""You extract obligations from contract clauses for an obligation tracker.
Reply with ONLY a JSON object: {{"obligations": [{{
  "description": "what must be done, business-friendly, one sentence",
  "obligated_party": "who must do it (party name or role as written)",
  "obligation_type": "one of {OBLIGATION_TYPES}",
  "due_date": "ISO date, recurring schedule (e.g. 'quarterly'), or relative deadline (e.g. 'within 45 days of invoice'); null if none",
  "trigger": "event that triggers it, or null",
  "source_clause_id": "MUST be one of the bracketed ids provided",
  "source_quote": "short sentence copied VERBATIM from that clause"
}}]}}
Rules: only concrete obligations (a party must do or refrain from something). No duplicates.
An empty list is valid. Never invent clause ids."""


def extract_obligations(clauses: list[Clause]) -> list[dict]:
    by_id = {c.clause_id: c for c in clauses}
    out: list[dict] = []
    for i in range(0, len(clauses), CLAUSE_BATCH_SIZE):
        batch = clauses[i:i + CLAUSE_BATCH_SIZE]
        try:
            data = chat_json(
                [{"role": "system", "content": OBLIGATIONS_PROMPT},
                 {"role": "user", "content": _clause_block(batch)}],
                model=settings.extract_model, max_tokens=4000,
            )
        except Exception:
            log.exception("Obligation extraction failed for batch %s", i)
            continue
        for item in data.get("obligations", []) if isinstance(data, dict) else []:
            cid = _resolve_clause_id(item.get("source_clause_id"), batch, by_id)
            if not cid or not item.get("description"):
                continue
            otype = item.get("obligation_type") or "other"
            out.append({
                "id": uuid.uuid4().hex[:12],
                "description": str(item["description"])[:1000],
                "obligated_party": (item.get("obligated_party") or None),
                "obligation_type": otype if otype in OBLIGATION_TYPES else "other",
                "due_date": item.get("due_date") or None,
                "trigger": item.get("trigger") or None,
                "source_clause_id": cid,
                "source_quote": (item.get("source_quote") or None),
            })
    return out


# ---------------------------------------------------------------- risks (LLM)

RISKS_PROMPT = f"""You are a contract risk reviewer. Identify commercial/legal/compliance/delivery risks in the clauses.
Reply with ONLY a JSON object: {{"risks": [{{
  "category": "one of {RISK_CATEGORIES}",
  "severity": "high|medium|low",
  "title": "short risk headline (max 10 words)",
  "rationale": "1-2 sentences: why this is a risk for the customer",
  "source_clause_id": "MUST be one of the bracketed ids provided",
  "source_quote": "short passage copied VERBATIM from that clause"
}}]}}
Severity rubric:
- high: material one-sided exposure â€” e.g. unlimited/uncapped liability, auto-renewal with under 30 days' notice, personal data processed without a data processing agreement, unilateral price increases, termination only for one party.
- medium: unfavorable but negotiable â€” e.g. long payment terms, broad indemnities, strict SLAs with credits, audit on short notice.
- low: standard-but-noteworthy terms worth tracking.
Only flag genuine risks (empty list is valid). Never invent clause ids."""


def extract_risks_llm(clauses: list[Clause]) -> list[dict]:
    by_id = {c.clause_id: c for c in clauses}
    out: list[dict] = []
    for i in range(0, len(clauses), CLAUSE_BATCH_SIZE):
        batch = clauses[i:i + CLAUSE_BATCH_SIZE]
        try:
            data = chat_json(
                [{"role": "system", "content": RISKS_PROMPT},
                 {"role": "user", "content": _clause_block(batch)}],
                model=settings.extract_model, max_tokens=4000,
            )
        except Exception:
            log.exception("Risk extraction failed for batch %s", i)
            continue
        for item in data.get("risks", []) if isinstance(data, dict) else []:
            cid = _resolve_clause_id(item.get("source_clause_id"), batch, by_id)
            if not cid or not item.get("title"):
                continue
            cat = item.get("category") or "legal"
            sev = item.get("severity") or "medium"
            out.append({
                "id": uuid.uuid4().hex[:12],
                "category": cat if cat in RISK_CATEGORIES else "legal",
                "severity": sev if sev in SEVERITIES else "medium",
                "title": str(item["title"])[:250],
                "rationale": item.get("rationale") or None,
                "source_clause_id": cid,
                "source_quote": item.get("source_quote") or None,
                "flagged_by": "llm",
            })
    return out


# ---------------------------------------------------------- risks (rule layer)

def _sentence_around(text: str, match: re.Match) -> str:
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    end = end + 1 if end != -1 else min(len(text), match.end() + 200)
    return text[start:end].strip()[:400]


def rule_based_risks(clauses: list[Clause]) -> list[dict]:
    """3 deterministic always-flag patterns. flagged_by='rule' shows in the UI."""
    risks: list[dict] = []

    def add(category: str, title: str, rationale: str, clause: Clause, quote: str) -> None:
        risks.append({
            "id": uuid.uuid4().hex[:12], "category": category, "severity": "high",
            "title": title, "rationale": rationale,
            "source_clause_id": clause.clause_id, "source_quote": quote,
            "flagged_by": "rule",
        })

    for c in clauses:
        low = c.text.lower()

        # 1. Unlimited liability
        m = re.search(r"unlimited\s+(?:\w+\s+){0,3}liab\w*|liab\w*[^.]{0,60}\bunlimited\b", low)
        if m:
            add("legal", "Unlimited liability exposure",
                "Liability is expressed as unlimited â€” no cap protects against open-ended exposure.",
                c, _sentence_around(c.text, m))

        # 2. Auto-renewal with short notice window (< 30 days)
        if re.search(r"automatic\w*\s+renew|auto-?renew|renews?\s+for\s+successive", low):
            # matches "15 days", "(15) days", "fifteen (15) days"
            dm = re.search(r"(\d{1,3})\s*\)?\s*(?:calendar\s+|business\s+)?days?", low)
            if dm and int(dm.group(1)) < 30:
                add("termination_renewal",
                    f"Auto-renewal with only {dm.group(1)} days' notice",
                    "The agreement renews automatically and the opt-out window is under 30 days â€” easy to miss and creates lock-in.",
                    c, _sentence_around(c.text, dm))

    # 3. Personal data processed but no DPA anywhere in the contract
    pd_clauses = [c for c in clauses if re.search(r"personal data|personally identifiable", c.text, re.I)]
    has_dpa = any(re.search(r"data processing agreement|\bDPA\b", c.text) for c in clauses)
    if pd_clauses and not has_dpa:
        # anchor to the data-protection clause when there is one
        c = next((x for x in pd_clauses if x.clause_type == "data_protection"), pd_clauses[0])
        m = re.search(r"personal data|personally identifiable", c.text, re.I)
        add("compliance", "Personal data processed without a DPA",
            "The contract involves processing personal data but no Data Processing Agreement is referenced â€” a compliance gap (e.g. GDPR Art. 28).",
            c, _sentence_around(c.text, m) if m else c.text[:200])

    return risks


def merge_risks(llm_risks: list[dict], rule_risks: list[dict]) -> list[dict]:
    """Rules always win on the same (clause, category) â€” drop the LLM duplicate."""
    rule_keys = {(r["source_clause_id"], r["category"]) for r in rule_risks}
    kept = [r for r in llm_risks if (r["source_clause_id"], r["category"]) not in rule_keys]
    return rule_risks + kept


# ---------------------------------------------------------------- summary

SUMMARY_PROMPT = """Write a business-friendly summary of this contract for a non-lawyer stakeholder.
Structure: one plain-English paragraph (what the deal is, who does what, money, term), then
3-5 bullet points starting with '- ' covering the most important obligations and risks.
No legalese, no preamble, under 220 words total."""


def generate_summary(full_text: str, meta: ContractMeta, top_risks: list[dict]) -> str:
    risk_lines = "\n".join(f"- [{r['severity']}] {r['title']}" for r in top_risks[:6]) or "none flagged"
    user = (
        f"Contract metadata: {meta.model_dump_json()}\n\n"
        f"Top flagged risks:\n{risk_lines}\n\n"
        f"Contract text (may be truncated):\n{full_text[:16000]}"
    )
    return chat_text(
        [{"role": "system", "content": SUMMARY_PROMPT}, {"role": "user", "content": user}],
        model=settings.extract_model, max_tokens=600,
    ).strip()
