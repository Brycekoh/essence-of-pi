"""Gemini implementation of `LLMClient`.

The important line in this file is `response_schema=schema`. Handing the SDK a
pydantic model constrains decoding to valid JSON of that shape, so there is no
"respond only in JSON" instruction in any prompt, no markdown fence to strip,
and no regex to recover from a model that decided to be chatty. `.parsed`
comes back as the model instance.

The rest of this file is shaped by one measured fact about the free tier:

    quotaId: GenerateRequestsPerDayPerProjectPerModel
    quotaValue: 20

Twenty requests per day, **per model**. That inverts the usual retry
instinct. Retrying is not free here -- every attempt spends a unit of the
scarcest resource, so a generous retry policy burns the day's budget on a
queue that is not moving. An earlier version of this file retried four times
across two models, turning one logical call into eight requests, and exhausted
the quota in a single test run.

So: retry each model **once**, then move to the next model. The quota is
per-model, so a rotation across several models multiplies the budget in a way
that retrying one model never can.
"""

import asyncio
import random
from typing import Optional, Sequence, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from .base import LLMError, LLMNotConfigured

T = TypeVar("T", bound=BaseModel)

# Retried once: the model is up but busy, and a short wait may clear it.
_RETRYABLE = (genai_errors.ServerError,)

# One wait, then give up on this model and try the next. Long enough to
# outlast a brief spike, short enough not to strand a request behind it.
_RETRY_WAIT = 3.0


class GeminiClient:
    def __init__(self, api_key: Optional[str], models: Sequence[str]):
        if not api_key:
            raise LLMNotConfigured(
                "GEMINI_API_KEY is not set. Get a key at "
                "https://aistudio.google.com/apikey and put it in backend/.env"
            )
        if not models:
            raise LLMNotConfigured("No models configured. Set LLM_MODEL.")

        self._client = genai.Client(api_key=api_key)
        self.models = tuple(dict.fromkeys(models))  # de-duplicate, keep order
        self.model = self.models[0]
        # Which model actually answered, so callers can report it honestly.
        self.last_model = self.model
        # Models that returned 429 in this process. Their daily quota is gone,
        # so re-trying them today would spend a request to learn nothing.
        self.exhausted: set[str] = set()

    def _candidates(self) -> list[str]:
        available = [m for m in self.models if m not in self.exhausted]
        # If everything is marked exhausted, the marks are probably stale
        # (a new day, a new process). Try the primary rather than refuse.
        return available or [self.model]

    async def structured(
        self,
        *,
        prompt: str,
        schema: type[T],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )

        errors: list[str] = []
        for model in self._candidates():
            try:
                parsed = await self._try_model(model, prompt, config, schema)
            except _TryNext as exc:
                errors.append(f"{model}: {exc.reason}")
                continue
            self.last_model = model
            return parsed

        raise LLMError(
            "No model answered. " + "; ".join(errors)
            + ". On the free tier each model allows 20 requests per day;"
            " add more models to LLM_FALLBACK_MODELS or enable billing."
        )

    async def _try_model(self, model, prompt, config, schema: type[T]) -> T:
        """One model, one retry. Raises `_TryNext` to move on."""
        for attempt in (1, 2):
            try:
                response = await self._client.aio.models.generate_content(
                    model=model, contents=prompt, config=config
                )
            except _RETRYABLE as exc:
                if attempt == 2:
                    raise _TryNext(f"busy ({_code(exc)})") from exc
                # Jitter so parallel requests do not retry in lockstep.
                await asyncio.sleep(_RETRY_WAIT + random.uniform(0, 1.0))
                continue
            except genai_errors.ClientError as exc:
                if _code(exc) == 429:
                    # Daily quota for this model is spent. Never retry it --
                    # that is a request bought for no information.
                    self.exhausted.add(model)
                    raise _TryNext("daily quota exhausted") from exc
                # A malformed request or a bad key fails identically on every
                # model, so there is nothing to fall back to.
                raise LLMError(f"Gemini rejected the request: {exc}") from exc

            parsed = response.parsed
            if parsed is None:
                # Reachable when the model hits a stop reason mid-object --
                # a token limit, or a safety filter.
                raise LLMError(
                    "Gemini returned no parsable content "
                    f"(finish reason: {_finish_reason(response)})."
                )
            if not isinstance(parsed, schema):
                try:
                    parsed = schema.model_validate(parsed)
                except ValidationError as exc:
                    raise LLMError(f"Response did not match the schema: {exc}") from exc
            return parsed

        raise _TryNext("exhausted attempts")  # unreachable, kept for clarity


class _TryNext(Exception):
    """Internal: this model is no good right now, try the next one."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _code(exc: Exception) -> int:
    return getattr(exc, "code", 0) or 0


def _finish_reason(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        return str(getattr(candidates[0], "finish_reason", "unknown"))
    return "unknown"
