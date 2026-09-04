"""The seam between this app and whichever LLM is behind it.

One method, `structured`: given a prompt and a pydantic model, return an
instance of that model. Everything the app asks an LLM for -- concepts now,
scene splits and Manim code later -- is a structured request, so this is the
only shape the rest of the codebase needs to know about.

Deliberately *not* here: prompts. Those live with the feature that owns them
(`services/concepts.py`), so swapping providers never means rewriting prompts.
"""

from typing import Optional, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Any failure to get a usable answer out of the model."""


class LLMNotConfigured(LLMError):
    """No provider credentials are present."""


class LLMClient(Protocol):
    """Structural type -- implementations don't inherit from this."""

    model: str

    async def structured(
        self,
        *,
        prompt: str,
        schema: type[T],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> T:
        """Return an instance of `schema`, or raise `LLMError`."""
        ...
