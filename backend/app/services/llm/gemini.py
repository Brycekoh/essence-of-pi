"""Gemini implementation of `LLMClient`.

The important line in this file is `response_schema=schema`. Handing the SDK a
pydantic model constrains decoding to valid JSON of that shape, so there is no
"respond only in JSON" instruction in any prompt, no markdown fence to strip,
and no regex to recover from a model that decided to be chatty. `.parsed`
comes back as the model instance.
"""

import asyncio
import random
from typing import Optional, TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from .base import LLMError, LLMNotConfigured

T = TypeVar("T", bound=BaseModel)

# Retried: the model is up but busy, or the request tripped a transient limit.
# Not retried: a malformed request or a bad key, which will fail identically
# every time.
_RETRYABLE = (genai_errors.ServerError,)
_MAX_ATTEMPTS = 3


class GeminiClient:
    def __init__(self, api_key: Optional[str], model: str):
        if not api_key:
            raise LLMNotConfigured(
                "GEMINI_API_KEY is not set. Get a key at "
                "https://aistudio.google.com/apikey and put it in backend/.env"
            )
        self._client = genai.Client(api_key=api_key)
        self.model = model

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

        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
            except _RETRYABLE as exc:
                last_error = exc
                if attempt == _MAX_ATTEMPTS:
                    break
                # Exponential backoff with jitter, so a burst of parallel
                # requests doesn't retry in lockstep and re-collide.
                await asyncio.sleep((2 ** (attempt - 1)) + random.uniform(0, 0.3))
                continue
            except genai_errors.APIError as exc:
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
                # Belt and braces: the SDK has already validated, but a schema
                # change should fail loudly here rather than downstream.
                try:
                    parsed = schema.model_validate(parsed)
                except ValidationError as exc:
                    raise LLMError(f"Response did not match the schema: {exc}") from exc
            return parsed

        raise LLMError(f"Gemini unavailable after {_MAX_ATTEMPTS} attempts: {last_error}")


def _finish_reason(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        return str(getattr(candidates[0], "finish_reason", "unknown"))
    return "unknown"
