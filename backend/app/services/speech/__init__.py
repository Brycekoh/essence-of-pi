from functools import lru_cache

from .base import Speech, SpeechError
from .gtts_speech import GttsSpeech
from .piper_speech import PiperSpeech
from .stub import StubSpeech

__all__ = [
    "Speech",
    "SpeechError",
    "GttsSpeech",
    "PiperSpeech",
    "StubSpeech",
    "build_speech",
]


@lru_cache
def build_speech(
    engine: str,
    *,
    image: str,
    voice: str,
    sentence_silence: float,
    length_scale: float,
    lang: str,
    tld: str,
    memory: str,
    cpus: str,
    docker_bin: str,
) -> Speech:
    """Return the configured narrator.

    Two engines, one interface. `piper` runs in the render image: no key, no
    quota, no network, and the same audio every time. `gtts` is kept as a
    fallback for anyone who would rather not build the image.
    """
    if engine == "gtts":
        return GttsSpeech(lang=lang, tld=tld)
    if engine == "piper":
        return PiperSpeech(
            image=image,
            voice=voice,
            sentence_silence=sentence_silence,
            length_scale=length_scale,
            memory=memory,
            cpus=cpus,
            docker_bin=docker_bin,
        )
    raise SpeechError(f"Unknown speech engine {engine!r}. Use 'piper' or 'gtts'.")
