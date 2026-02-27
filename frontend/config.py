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


class Settings:
    """All environment-derived configuration. Loaded once at import. No defaults."""

    def __init__(self) -> None:
        load_dotenv()
        base = _required("API_BASE").rstrip("/")
        self.api_base = base
        self.chat_api = f"{base}/api/chat/"
        self.search_api = f"{base}/api/search/"
        self.graph_svg_url = f"{base}/api/graph/svg"
        self.mitre_version_url = f"{base}/api/mitre/version"
        self.mitre_list_url = f"{base}/api/mitre/list"
        self.mitre_content_url = f"{base}/api/mitre/"

    def mitre_download_url(self, version: str | None = None) -> str:
        url = f"{self.api_base}/api/mitre/"
        if version and version.strip():
            return f"{url}?version={version.strip()}"
        return url

    def mitre_download_proxy_path(self, version: str | None = None) -> str:
        """Relative path for frontend proxy so browser uses same origin (backend port may be inaccessible)."""
        path = "/api/proxy/mitre/download"
        if version and version.strip():
            return f"{path}?version={version.strip()}"
        return path


# Single instance loaded at import
settings = Settings()
