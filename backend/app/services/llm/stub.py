"""A scripted `LLMClient` for tests.

Queue the responses you want, then assert on what the app asked for. No
network, no key, no flakiness -- which is the whole reason the protocol in
`base.py` exists.
"""

from typing import Any, Optional, TypeVar

from pydantic import BaseModel

from .base import LLMError

T = TypeVar("T", bound=BaseModel)


class StubLLM:
    model = "stub"

    def __init__(self, responses: Optional[list[Any]] = None):
        self.responses: list[Any] = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def queue(self, response: Any) -> "StubLLM":
        self.responses.append(response)
        return self

    async def structured(
        self,
        *,
        prompt: str,
        schema: type[T],
        system: Optional[str] = None,
        temperature: float = 0.2,
    ) -> T:
        self.calls.append(
            {
                "prompt": prompt,
                "schema": schema,
                "system": system,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise AssertionError("StubLLM was called more times than it has responses.")

        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, schema):
            raise LLMError(
                f"StubLLM was queued a {type(response).__name__} "
                f"but the caller asked for {schema.__name__}."
            )
        return response
