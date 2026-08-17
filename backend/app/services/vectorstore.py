"""Vector storage behind one small interface.

QdrantStore is the primary (docker-compose). LocalStore is a dependency-free
fallback (SQLite + numpy cosine) so the stack runs on machines without Docker.
`VECTOR_BACKEND=auto` probes Qdrant once and falls back gracefully.
"""
from __future__ import annotations
import json
import logging
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from app.config import resolved_data_dir, settings

log = logging.getLogger(__name__)

COLLECTION = "clauses"


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, points: list[dict[str, Any]]) -> None:
        """points: [{'id': clause_id, 'vector': [...], 'payload': {...}}]"""

    @abstractmethod
    def search(self, vector: list[float], contract_id: str, top_k: int = 20,
               clause_type: str | None = None) -> list[tuple[dict, float]]:
        """Returns [(payload, score)] sorted by score desc."""


def _point_uuid(clause_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, clause_id))


class QdrantStore(VectorStore):
    def __init__(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.client = QdrantClient(url=settings.qdrant_url, timeout=20)
        if not self.client.collection_exists(COLLECTION):
            self.client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
            )
        for field in ("contract_id", "clause_type"):
            try:
                self.client.create_payload_index(COLLECTION, field_name=field, field_schema="keyword")
            except Exception:
                pass  # already exists

    def upsert(self, points: list[dict[str, Any]]) -> None:
        from qdrant_client.models import PointStruct

        structs = [
            PointStruct(id=_point_uuid(p["id"]), vector=p["vector"],
                        payload={**p["payload"], "clause_id": p["id"]})
            for p in points
        ]
        self.client.upsert(collection_name=COLLECTION, points=structs, wait=True)

    def search(self, vector, contract_id, top_k=20, clause_type=None):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        must = [FieldCondition(key="contract_id", match=MatchValue(value=contract_id))]
        if clause_type:
            must.append(FieldCondition(key="clause_type", match=MatchValue(value=clause_type)))
        hits = self.client.search(
            collection_name=COLLECTION, query_vector=vector,
            query_filter=Filter(must=must), limit=top_k, with_payload=True,
        )
        return [(h.payload or {}, float(h.score)) for h in hits]


class LocalStore(VectorStore):
    """SQLite-backed store with in-process cosine search. Plenty for demo scale."""

    def __init__(self) -> None:
        self.path = resolved_data_dir() / "vectors.db"
        self._lock = threading.Lock()
        with self._conn() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS vectors ("
                "clause_id TEXT PRIMARY KEY, contract_id TEXT, clause_type TEXT,"
                "payload TEXT, vec BLOB)"
            )
            con.execute("CREATE INDEX IF NOT EXISTS ix_vec_contract ON vectors(contract_id)")

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def upsert(self, points):
        rows = [
            (
                p["id"],
                p["payload"].get("contract_id", ""),
                p["payload"].get("clause_type", ""),
                json.dumps({**p["payload"], "clause_id": p["id"]}),
                np.asarray(p["vector"], dtype=np.float32).tobytes(),
            )
            for p in points
        ]
        with self._lock, self._conn() as con:
            con.executemany(
                "INSERT OR REPLACE INTO vectors (clause_id, contract_id, clause_type, payload, vec) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def search(self, vector, contract_id, top_k=20, clause_type=None):
        q = "SELECT payload, vec FROM vectors WHERE contract_id = ?"
        args: list[Any] = [contract_id]
        if clause_type:
            q += " AND clause_type = ?"
            args.append(clause_type)
        with self._lock, self._conn() as con:
            rows = con.execute(q, args).fetchall()
        if not rows:
            return []
        qv = np.asarray(vector, dtype=np.float32)
        qv = qv / (np.linalg.norm(qv) + 1e-9)
        mat = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
        mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        sims = mat @ qv
        order = np.argsort(-sims)[:top_k]
        return [(json.loads(rows[i][0]), float(sims[i])) for i in order]


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_store() -> VectorStore:
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is not None:
            return _store
        backend = settings.vector_backend.lower()
        if backend in ("qdrant", "auto"):
            try:
                _store = QdrantStore()
                log.info("Vector backend: Qdrant at %s", settings.qdrant_url)
                return _store
            except Exception as e:
                if backend == "qdrant":
                    raise
                log.warning("Qdrant unreachable (%s) â€” falling back to local vector store", e)
        _store = LocalStore()
        log.info("Vector backend: local SQLite store")
        return _store
