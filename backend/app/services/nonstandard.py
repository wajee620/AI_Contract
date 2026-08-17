"""Non-standard clause detection.

Each extracted clause is embedded and compared to the nearest standard clause of
the same type from a small synthetic library. Below the similarity threshold the
clause is flagged, and a single LLM call explains the deviation (shown as a
side-by-side diff in the UI).
"""
import json
import logging
from functools import lru_cache

import numpy as np

from app.config import resolved_data_dir, settings
from app.db.models import Clause
from app.llm.gateway import chat_text, embed

log = logging.getLogger(__name__)

MAX_EXPLANATIONS = 8  # cap LLM calls per contract


@lru_cache(maxsize=1)
def _standard_library() -> list[dict]:
    """[{'type', 'title', 'text', 'vector'}] — embedded once per process."""
    path = resolved_data_dir() / "standard_clauses.json"
    if not path.exists():
        log.warning("No standard clause library at %s — skipping non-standard detection", path)
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    vectors = embed([e["text"] for e in entries])
    for e, v in zip(entries, vectors):
        e["vector"] = np.asarray(v, dtype=np.float32)
    return entries


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))


EXPLAIN_PROMPT = """Compare a contract clause against the standard market wording of the same type.
In 2-3 plain-English sentences, explain how the actual clause deviates from the standard and why
that matters commercially. No preamble."""


def analyze_nonstandard(clauses: list[Clause], clause_vectors: dict[str, list[float]]) -> None:
    """Mutates Clause rows in place (caller commits)."""
    library = _standard_library()
    if not library:
        return
    types_available = {e["type"] for e in library}
    explained = 0

    for c in clauses:
        if c.clause_type not in types_available or c.clause_id not in clause_vectors:
            continue
        cvec = np.asarray(clause_vectors[c.clause_id], dtype=np.float32)
        best = max((e for e in library if e["type"] == c.clause_type),
                   key=lambda e: _cosine(cvec, e["vector"]))
        sim = _cosine(cvec, best["vector"])
        c.nonstandard_similarity = round(sim, 4)
        c.standard_title = best["title"]
        c.standard_text = best["text"]
        if sim < settings.nonstandard_sim_threshold:
            c.nonstandard = True
            if explained < MAX_EXPLANATIONS:
                try:
                    c.nonstandard_explanation = chat_text(
                        [{"role": "system", "content": EXPLAIN_PROMPT},
                         {"role": "user",
                          "content": f"STANDARD ({best['title']}):\n{best['text']}\n\nACTUAL CLAUSE:\n{c.text[:3000]}"}],
                        model=settings.extract_model, max_tokens=300,
                    ).strip()
                    explained += 1
                except Exception:
                    log.exception("Deviation explanation failed for %s", c.clause_id)
