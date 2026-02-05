"""
Application settings loaded from environment variables at startup.
Import `settings` and use it instead of reading os.environ elsewhere.
Raises RuntimeError if any required variable is missing.
"""
import os

from dotenv import load_dotenv


def _required(key: str) -> str:
    value = os.environ.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value.strip()


def _required_int(key: str) -> int:
    s = _required(key)
    try:
        return int(s)
    except ValueError as e:
        raise RuntimeError(f"Environment variable {key} must be an integer: {s!r}") from e


class Settings:
    """All environment-derived configuration. Loaded once at import. No defaults."""

    def __init__(self) -> None:
        load_dotenv()
        # MongoDB
        self.mongodb_uri = _required("MONGODB_URI")
        print(self.mongodb_uri)
        self.vector_search_index_name = _required("VECTOR_SEARCH_INDEX_NAME")

        # Neo4j
        self.neo4j_uri = _required("NEO4J_URI")
        self.neo4j_user = _required("NEO4J_USER")
        self.neo4j_password = _required("NEO4J_PASSWORD")

        # LM Studio / Ollama (OpenAI-compatible API)
        _lm_base = _required("LM_STUDIO_URI").rstrip("/")
        if not _lm_base.endswith("/v1"):
            _lm_base = _lm_base + "/v1"
        self.lm_studio_base_url = _lm_base
        self.lm_studio_api_key = _required("LM_STUDIO_API_KEY")
        self.chat_model = _required("CHAT_MODEL")
        self.embedding_model = _required("EMBEDDING_MODEL")
        self.rag_top_k = _required_int("RAG_TOP_K")

        # Test / external API base (e.g. for test_mitre.py)
        self.mitre_api_base = _required("MITRE_API_BASE").rstrip("/")


# Single instance loaded at import
settings = Settings()
