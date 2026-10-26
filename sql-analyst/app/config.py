"""Settings read from the environment (and .env)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    database_url: str = os.getenv("DATABASE_URL", "")
    min_seconds_between_llm_calls: float = float(os.getenv("MIN_SECONDS_BETWEEN_LLM_CALLS", "6"))
    max_attempts: int = int(os.getenv("MAX_ATTEMPTS", "3"))
    row_limit: int = int(os.getenv("ROW_LIMIT", "100"))
    statement_timeout_seconds: int = int(os.getenv("STATEMENT_TIMEOUT_SECONDS", "10"))


settings = Settings()
