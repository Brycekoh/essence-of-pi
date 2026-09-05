from functools import lru_cache
from typing import Optional

from .base import LLMClient, LLMError, LLMNotConfigured
from .gemini import GeminiClient
from .stub import StubLLM

__all__ = [
    "LLMClient",
    "LLMError",
    "LLMNotConfigured",
    "GeminiClient",
    "StubLLM",
    "build_llm",
]


@lru_cache
def build_llm(api_key: Optional[str], models_csv: str) -> LLMClient:
    """Return a client for the configured provider.

    `models_csv` rather than a list because `lru_cache` needs hashable
    arguments -- and caching matters here so a request does not pay to
    construct an HTTP client, and so the set of quota-exhausted models is
    remembered across calls instead of being rediscovered one wasted request
    at a time.

    Adding a provider means a module beside `gemini.py` and one branch here.
    Nothing above this layer changes.
    """
    models = [m.strip() for m in models_csv.split(",") if m.strip()]
    return GeminiClient(api_key=api_key, models=models)
