"""Ingestion orchestrator: parse -> chunk -> index -> extract -> risk -> nonstandard -> summary.

Runs as a FastAPI background task; updates Contract.status/progress so the UI
can poll. Any failure marks the contract 'failed' with the error message.
"""
import logging

from app.db.database import SessionLocal
from app.db.models import Clause, Contract, Obligation, Risk
from app.llm.gateway import embed
from app.schemas import ContractMeta
from app.services import extraction
from app.services.chunking import classify_clause_type, make_clause_id, split_into_clauses
from app.services.nonstandard import analyze_nonstandard
from app.services.parsing import parse_document
from app.services.vectorstore import get_store

log = logging.getLogger(__name__)


def run_ingestion(contract_id: str, file_path: str) -> None:
    db = SessionLocal()

    def set_status(status: str, progress: str) -> None:
        contract = db.get(Contract, contract_id)
        if contract is not None:
            contract.status = status
            contract.progress = progress
            db.commit()

    try:
        # 1. Parse (text layer detection + vision OCR for scanned pages)
        set_status("parsing", "Reading document, detecting text layers")
        pages = parse_document(file_path, progress=lambda msg: set_status("parsing", msg))
        full_text = "\n\n".join(p.text for p in pages)

        # 2. Clause-aware chunking
        set_status("chunking", "Splitting into clauses")
        raw_chunks = split_into_clauses(pages)
        used_ids: set[str] = set()
        clauses: list[Clause] = []
        for i, ch in enumerate(raw_chunks):
            clauses.append(Clause(
                clause_id=make_clause_id(contract_id, ch, i, used_ids),
                contract_id=contract_id,
                section=ch.section,
                heading=ch.heading,
                clause_type=classify_clause_type(ch.heading, ch.text),
                page=ch.page,
                chunk_index=i,
                text=ch.text,
                is_scanned=ch.is_scanned,
            ))
        db.add_all(clauses)
        db.commit()

        # 3. Index: embeddings -> vector store (dense); BM25 reads from SQL at query time
        set_status("indexing", f"Embedding {len(clauses)} clauses")
        vectors = embed([f"{c.heading or ''}\n{c.text}" for c in clauses])
        clause_vectors = {c.clause_id: v for c, v in zip(clauses, vectors)}
        get_store().upsert([
            {"id": c.clause_id, "vector": v,
             "payload": {"contract_id": contract_id, "clause_type": c.clause_type,
                         "section": c.section, "page": c.page}}
            for c, v in zip(clauses, vectors)
        ])

        # 4. Structured extraction
        set_status("extracting", "Extracting contract metadata")
        meta = extraction.extract_contract_meta(full_text)
        contract = db.get(Contract, contract_id)
        contract.meta_json = meta.model_dump()
        db.commit()

        set_status("extracting", "Extracting obligations")
        for ob in extraction.extract_obligations(clauses):
            db.add(Obligation(contract_id=contract_id, **ob))
        db.commit()

        # 5. Risks: LLM rubric + deterministic rule layer
        set_status("analyzing", "Identifying risks (LLM + rules)")
        merged = extraction.merge_risks(
            extraction.extract_risks_llm(clauses),
            extraction.rule_based_risks(clauses),
        )
        for rk in merged:
            db.add(Risk(contract_id=contract_id, **rk))
        db.commit()

        # 6. Non-standard clause detection (reuses the clause embeddings)
        set_status("analyzing", "Comparing clauses against standard library")
        analyze_nonstandard(clauses, clause_vectors)
        db.commit()

        # 7. Business-friendly summary
        set_status("summarizing", "Writing business summary")
        contract = db.get(Contract, contract_id)
        try:
            contract.summary = extraction.generate_summary(
                full_text, ContractMeta.model_validate(contract.meta_json or {}), merged)
        except Exception:
            log.exception("Summary generation failed")
        contract.status = "done"
        contract.progress = "Complete"
        db.commit()
        log.info("Ingestion complete for %s: %d clauses", contract_id, len(clauses))

    except Exception as e:
        log.exception("Ingestion failed for %s", contract_id)
        db.rollback()
        try:
            set_status("failed", f"{type(e).__name__}: {e}"[:500])
        except Exception:
            pass
    finally:
        db.close()
