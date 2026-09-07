"""The dependency providers, against real Settings.

Why this file exists: every other test overrides `provide_llm`,
`provide_speech`, `provide_renderer` and `provide_media` with stubs, which is
what keeps the suite offline and fast. The cost is that nothing ever ran the
real providers -- so `deps.py` spent a while reading `settings.speech_engine`,
`settings.kokoro_voice` and three other attributes that did not exist on
`Settings` at all. Every test passed. Any real video request would have
returned a 500.

A test double that replaces a collaborator also replaces the check that the
collaborator can be built.
"""

import pytest
from fastapi import HTTPException

from app.api.deps import provide_llm, provide_media, provide_renderer, provide_speech
from app.config import Settings
from app.services.speech import GttsSpeech, KokoroSpeech, PiperSpeech


def test_providers_build_from_real_settings():
    """The check the stubs were quietly skipping."""
    settings = Settings()

    assert provide_speech(settings) is not None
    assert provide_renderer(settings) is not None
    assert provide_media(settings) is not None

    try:
        provide_llm(settings)
    except HTTPException as exc:
        # No API key configured is a legitimate outcome and returns 503.
        # An AttributeError is not, and would fail this test loudly.
        assert exc.status_code == 503


@pytest.mark.parametrize(
    "engine, expected",
    [("kokoro", KokoroSpeech), ("piper", PiperSpeech), ("gtts", GttsSpeech)],
)
def test_every_engine_can_be_built_from_settings(engine, expected):
    settings = Settings(speech_engine=engine)
    assert isinstance(provide_speech(settings), expected)


def test_settings_names_match_what_deps_reads():
    """Catch a renamed or dropped setting before a request does."""
    settings = Settings()
    for name in (
        "speech_engine",
        "speech_sentence_silence",
        "speech_length_scale",
        "speech_noise_scale",
        "speech_noise_w_scale",
        "piper_voice",
        "kokoro_image",
        "kokoro_voice",
        "kokoro_speed",
        "renderer_image",
        "render_memory",
        "render_cpus",
        "renderer_docker_bin",
    ):
        assert hasattr(settings, name), f"deps.py reads settings.{name}"
