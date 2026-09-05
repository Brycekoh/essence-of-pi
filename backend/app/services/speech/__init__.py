from functools import lru_cache

from .base import Speech, SpeechError
from .gtts_speech import GttsSpeech
from .stub import StubSpeech

__all__ = ["Speech", "SpeechError", "GttsSpeech", "StubSpeech", "build_speech"]


@lru_cache
def build_speech(lang: str, tld: str) -> Speech:
    return GttsSpeech(lang=lang, tld=tld)
