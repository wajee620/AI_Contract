from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All secrets/config come from env / .env. The .env at repo root is also
    found when running from backend/ (and is mounted at /app/.env in Docker)."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # TCS GenAI Lab gateway (OpenAI-compatible)
    api_endpoint: str = "https://genailab.tcs.in/"
    api_key: str = ""

    # Model routing per the locked design
    embed_model: str = "azure/genailab-maas-text-embedding-3-large"
    extract_model: str = "azure/genailab-maas-gpt-4.1"          # extraction + agents
    qa_model: str = "azure/genailab-maas-gpt-4.1-mini"          # Q&A, rerank, judge
    # Llama-3.2-90B-Vision (the original design choice) was retired by the
    # gateway (410 model_deprecated, verified 2026-07-07); gpt-4o won the
    # replacement bake-off on OCR accuracy + latency (scripts/check_models.py).
    ocr_model: str = "genailab-maas-gpt-4o"

    embedding_dim: int = 3072

    # Storage. Empty DATABASE_URL -> SQLite in DATA_DIR (lite mode, no Docker needed).
    database_url: str = ""
    qdrant_url: str = "http://localhost:6333"
    vector_backend: str = "auto"  # auto | qdrant | local

    data_dir: str = ""

    nonstandard_sim_threshold: float = 0.62
    agent_max_rounds: int = 3

    # MOCK_LLM=1 runs the whole stack offline with deterministic dummy outputs
    # (no gateway credentials needed) — for dev machines and pipeline tests.
    mock_llm: bool = False


settings = Settings()


def resolved_data_dir() -> Path:
    if settings.data_dir:
        p = Path(settings.data_dir)
    else:
        # repo-root/data whether we run from repo root or backend/
        for cand in (Path("data"), Path("../data")):
            if cand.is_dir():
                p = cand
                break
        else:
            p = Path("data")
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def resolved_database_url() -> str:
    if settings.database_url:
        return settings.database_url
    return f"sqlite:///{(resolved_data_dir() / 'app.db').as_posix()}"


def uploads_dir() -> Path:
    p = resolved_data_dir() / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p
