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
        GeminiClient(api_key=None, model="gemini-2.0-flash")
    assert "GEMINI_API_KEY" in str(exc.value)
    assert "aistudio.google.com" in str(exc.value), "tell the user where to get one"


def test_build_llm_caches_per_configuration():
    a = build_llm("key-one", "gemini-2.0-flash")
    b = build_llm("key-one", "gemini-2.0-flash")
    c = build_llm("key-two", "gemini-2.0-flash")

    assert a is b, "the same config reuses one HTTP client"
    assert a is not c
    assert a.model == "gemini-2.0-flash"
