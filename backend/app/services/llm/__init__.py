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
def build_llm(api_key: Optional[str], model: str) -> LLMClient:
    """Return a client for the configured provider.

    Cached on the arguments rather than reading settings itself, so tests can
    build one with different config without fighting a cached singleton -- and
    so a request doesn't pay to construct an HTTP client every time.

    Adding a provider means a module beside `gemini.py` and one branch here.
    Nothing above this layer changes.
    """
    return GeminiClient(api_key=api_key, model=model)
