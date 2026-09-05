"""Tests for the Gemini client that need no key and no network.

The valuable one is `test_schema_is_acceptable_to_the_sdk`: response schemas
are not arbitrary pydantic: unions, arbitrary defaults and some nested shapes
get rejected. Catching that here beats catching it in a 502 from production.
"""

import pytest
from google.genai import types

from app.models import ConceptExtraction
from app.services.llm import GeminiClient, LLMNotConfigured, build_llm


def test_schema_is_acceptable_to_the_sdk():
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ConceptExtraction,
    )
    assert config.response_schema is not None


def test_missing_key_raises_an_actionable_error():
    with pytest.raises(LLMNotConfigured) as exc:
        GeminiClient(api_key=None, models=["gemini-3.8-flash"])
    assert "GEMINI_API_KEY" in str(exc.value)
    assert "aistudio.google.com" in str(exc.value), "tell the user where to get one"


def test_build_llm_caches_per_configuration():
    a = build_llm("key-one", "gemini-3.8-flash")
    b = build_llm("key-one", "gemini-3.8-flash")
    c = build_llm("key-two", "gemini-3.8-flash")

    assert a is b, "the same config reuses one client, and one exhausted set"
    assert a is not c
    assert a.model == "gemini-3.8-flash"


def test_models_are_tried_in_order():
    client = GeminiClient(api_key="k", models=["a", "b", "c"])
    assert client._candidates() == ["a", "b", "c"]
    assert client.model == "a", "the first is the primary"


def test_duplicate_models_are_collapsed():
    """Retrying the same model twice buys nothing and costs a request."""
    client = GeminiClient(api_key="k", models=["a", "b", "a"])
    assert client.models == ("a", "b")


def test_quota_exhausted_models_are_skipped():
    """20 requests/day/model: re-trying a 429'd model buys no information."""
    client = GeminiClient(api_key="k", models=["a", "b"])
    client.exhausted.add("a")
    assert client._candidates() == ["b"]


def test_all_exhausted_falls_back_to_the_primary():
    """Stale marks from a previous day must not brick the client."""
    client = GeminiClient(api_key="k", models=["a", "b"])
    client.exhausted.update({"a", "b"})
    assert client._candidates() == ["a"]


def test_one_retry_per_model_not_four():
    """Retrying is not free on a per-request daily quota."""
    from app.services.llm.gemini import _RETRY_WAIT

    assert _RETRY_WAIT <= 5, "a long wait strands a request behind a busy model"
