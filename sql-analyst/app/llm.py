"""LLM factory and a rate-limit-safe call helper."""
import threading
import time
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import settings

MAX_TRIES = 3
_lock = threading.Lock()
_last_call = 0.0


class LLMError(RuntimeError):
    """The LLM call failed (rate limit still exceeded after retries, or another provider error)."""


@lru_cache
def get_llm() -> BaseChatModel:
    """The only place the model is created; swap the provider here."""
    if not settings.google_api_key:
        raise LLMError("GOOGLE_API_KEY is not set")
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=0,
        max_retries=0,  # call_llm owns retries
    )


def _is_rate_limit(e: Exception) -> bool:
    # 503 UNAVAILABLE ("model overloaded") is transient too, so it gets the same backoff.
    msg = str(e)
    return getattr(e, "code", None) in (429, 503) or any(s in msg for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE"))


def call_llm(prompt: str) -> str:
    """Send a prompt and return the text, spacing calls out and backing off on 429s."""
    global _last_call
    for attempt in range(MAX_TRIES):
        with _lock:  # one call at a time keeps the minimum gap meaningful across requests
            wait = settings.min_seconds_between_llm_calls - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            try:
                return get_llm().invoke(prompt).text
            except LLMError:
                raise
            except Exception as e:
                if not _is_rate_limit(e):
                    raise LLMError(f"LLM call failed: {e}") from e
                last_error = e
            finally:
                _last_call = time.monotonic()
        if attempt < MAX_TRIES - 1:
            time.sleep(max(settings.min_seconds_between_llm_calls, 2) * 2**attempt)
    raise LLMError(f"LLM still rate limited or overloaded after {MAX_TRIES} tries: {last_error}")
