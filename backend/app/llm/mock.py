"""Deterministic offline stand-ins for the gateway (set MOCK_LLM=1).

Lets the full pipeline and UI run with no gateway credentials: embeddings are
hashing-vectorizer vectors (real cosine/retrieval behaviour), chat replies are
schema-valid canned outputs selected by sniffing the calling prompt. Every
mock reply is clearly tagged [MOCK].
"""
import hashlib
import re
from types import SimpleNamespace

import numpy as np

from app.config import settings

_ID_RE = re.compile(r"\[([A-Za-z0-9.\-]{4,})\]")


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def embed(texts: list[str]) -> list[list[float]]:
    dim = settings.embedding_dim
    out = []
    for t in texts:
        v = np.zeros(dim, dtype=np.float32)
        for tok in _tokens(t)[:2000]:
            h = int(hashlib.md5(tok.encode()).hexdigest()[:8], 16)
            v[h % dim] += 1.0
        n = float(np.linalg.norm(v))
        out.append((v / n).tolist() if n else v.tolist())
    return out


def _system(messages: list[dict]) -> str:
    return " ".join(str(m.get("content", "")) for m in messages if m.get("role") == "system").lower()


def _ids(messages: list[dict]) -> list[str]:
    text = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
    seen: list[str] = []
    for m in _ID_RE.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def chat_text(messages: list[dict], **_kw) -> str:
    sys = _system(messages)
    ids = _ids(messages)
    if any(isinstance(m.get("content"), list) for m in messages):  # vision OCR call
        return "1. Mock OCR Clause\nThis page was transcribed offline by the mock OCR engine."
    if "business-friendly summary" in sys:
        return ("[MOCK] Offline dummy summary: this agreement is between two mock parties for a "
                "test service; fees, renewal and liability terms are placeholders.\n"
                "- Mock obligation highlight\n- Mock risk highlight\n- Set a valid api_key for real output")
    if "standard market wording" in sys:
        return "[MOCK] Dummy deviation explanation: wording differs from the standard clause."
    if "risk-review decision" in sys:
        return "[MOCK] Audit note: reviewer approved the flagged risks and dismissed none."
    if "contract analyst" in sys or "contract analysis agent" in sys:
        cite = f" [{ids[0]}]" if ids else ""
        return (f"[MOCK ANSWER] Based on the retrieved clause{cite}, the contract addresses this "
                f"point. Offline dummy reply — set a valid api_key for real answers.")
    return "[MOCK] ok"


def chat_json(messages: list[dict], **_kw):
    sys = _system(messages)
    ids = _ids(messages)
    if "contract metadata" in sys:
        return {"parties": ["MockCo Alpha Ltd.", "MockCo Beta GmbH"], "effective_date": "2026-01-01",
                "term": "6 months (mock)", "renewal_terms": "auto-renews, 10 days notice (mock)",
                "termination_terms": "30 days cure period (mock)", "governing_law": "Mockland",
                "total_value": "USD 6,000 (mock)"}
    if "obligation tracker" in sys:
        return {"obligations": [
            {"description": f"[MOCK] Dummy obligation extracted from clause {cid}",
             "obligated_party": "Provider", "obligation_type": "reporting", "due_date": "quarterly",
             "trigger": None, "source_clause_id": cid, "source_quote": None}
            for cid in ids[:3]
        ]}
    if "risk reviewer" in sys:
        if not ids:
            return {"risks": []}
        return {"risks": [
            {"category": "commercial", "severity": "medium", "title": "[MOCK] Dummy commercial risk",
             "rationale": "Deterministic placeholder emitted by mock LLM mode.",
             "source_clause_id": ids[0], "source_quote": None}
        ]}
    if "compare contracts across" in sys:
        user = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "user")
        cids = re.findall(r"### CONTRACT (\S+)", user)
        dims: list[str] = []
        for d in re.findall(r"^([A-Z][A-Za-z0-9 &/]+):$", user, re.M):
            if d not in dims:
                dims.append(d)
        return {"dimensions": [
            {"dimension": d,
             "findings": {cid: f"[MOCK] {d} terms retrieved for contract {cid}." for cid in cids},
             "assessment": f"[MOCK] Comparable {d.lower()} terms across the contracts."}
            for d in dims
        ], "verdict": "[MOCK] Offline comparison — the contracts are broadly comparable on the retrieved "
                      "dimensions. Set a valid api_key for a substantive verdict."}
    if "plan a comparison" in sys:
        return {"dimensions": [
            {"dimension": "Liability", "query": "limitation of liability cap", "clause_type": "liability"},
            {"dimension": "Term & Renewal", "query": "automatic renewal notice period", "clause_type": "renewal"},
            {"dimension": "Payment", "query": "fees payment terms", "clause_type": "payment"},
            {"dimension": "Data Protection", "query": "personal data processing DPA", "clause_type": "data_protection"},
        ]}
    if "rerank" in sys:
        return {"ranking": ids[:5]}
    if "faithfulness judge" in sys:
        return {"faithful": True, "note": "mock judge (offline mode)"}
    return {}


def chat_raw(messages: list[dict], **_kw):
    # No tool_calls: the agent loop answers without retrieving, which triggers
    # its guardrail and exercises the graceful fallback to single-shot RAG.
    return SimpleNamespace(content=chat_text(messages), tool_calls=None)
