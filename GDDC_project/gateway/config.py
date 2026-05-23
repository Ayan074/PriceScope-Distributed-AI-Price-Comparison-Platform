"""
Configuration settings for the gateway service.

Loads from environment variables with sensible defaults.
Defines all microservice URLs and distributed processing settings.
"""

import os
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings:
    """Application settings loaded from environment variables."""

    # ── Microservice URLs (each is a separate worker node) ──
    AMAZON_SERVICE_URL: str = os.getenv("AMAZON_SERVICE_URL", "http://localhost:8005")
    EBAY_SERVICE_URL: str = os.getenv("EBAY_SERVICE_URL", "http://localhost:8003")
    GOOGLE_SERVICE_URL: str = os.getenv("GOOGLE_SERVICE_URL", "http://localhost:8004")
    WALMART_SERVICE_URL: str = os.getenv("WALMART_SERVICE_URL", "http://localhost:8006")
    TARGET_SERVICE_URL: str = os.getenv("TARGET_SERVICE_URL", "http://localhost:8007")
    MCP_SERVER_URL: str = os.getenv("MCP_SERVER_URL", "http://localhost:8010")

    # ── LLM Settings ──
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # ── Redis (used for Celery broker + caching) ──
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # ── Cache ──
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))

    # ── App ──
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # ── Distributed Processing ──
    # Timeout for Celery group result collection (seconds)
    CELERY_RESULT_TIMEOUT: int = int(os.getenv("CELERY_RESULT_TIMEOUT", "30"))
    # Enable/disable Celery (falls back to async parallel if disabled)
    USE_CELERY: bool = os.getenv("USE_CELERY", "true").lower() == "true"

    @property
    def has_openai_key(self) -> bool:
        return bool(self.OPENAI_API_KEY and self.OPENAI_API_KEY != "sk-your-key-here")

    @property
    def service_urls(self) -> dict:
        """All registered microservice URLs. The orchestrator fans out to all of these."""
        return {
            "Amazon": self.AMAZON_SERVICE_URL,
            "eBay": self.EBAY_SERVICE_URL,
            "Google": self.GOOGLE_SERVICE_URL,
            "Walmart": self.WALMART_SERVICE_URL,
            "Target": self.TARGET_SERVICE_URL,
        }


settings = Settings()
