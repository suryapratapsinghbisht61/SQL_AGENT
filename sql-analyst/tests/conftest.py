import pytest
from sqlalchemy import text

from app import db


@pytest.fixture(scope="session")
def live_db():
    """Skip DB-backed tests when Postgres (docker compose) is not reachable."""
    try:
        with db.get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database not available: {e}")


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Fail loudly if any test reaches the real Gemini client."""
    from app import llm

    def boom():
        raise AssertionError("tests must not call the real LLM")

    monkeypatch.setattr(llm, "get_llm", boom)
