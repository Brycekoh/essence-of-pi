from functools import lru_cache
from typing import Optional

from .base import Speech, SpeechError
from .gtts_speech import GttsSpeech
from .kokoro_speech import KokoroSpeech
from .piper_speech import PiperSpeech
from .stub import StubSpeech

__all__ = [
    "Speech",
    "SpeechError",
    "GttsSpeech",
    "KokoroSpeech",
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
    noise_scale: Optional[float] = None,
    noise_w_scale: Optional[float] = None,
    kokoro_image: str = "essence-of-pi/tts:kokoro",
    kokoro_voice: str = "af_bella",
    kokoro_speed: float = 0.92,
) -> Speech:
    """Return the configured narrator.

    Three engines, one interface:

    - `kokoro` sounds the most human; its own 2.88 GB image, local, no key
    - `piper`  is far lighter and lives in the render image
    - `gtts`   needs no image at all, and sounds like a satnav

    All three are offline-capable except gtts, and none of them spend model
    quota -- which after milestone 4 is the resource that matters.
    """
    if engine == "gtts":
        return GttsSpeech(lang=lang, tld=tld)
    if engine == "piper":
        return PiperSpeech(
            image=image,
            voice=voice,
            sentence_silence=sentence_silence,
            length_scale=length_scale,
            noise_scale=noise_scale,
            noise_w_scale=noise_w_scale,
            memory=memory,
            cpus=cpus,
            docker_bin=docker_bin,
        )
    if engine == "kokoro":
        return KokoroSpeech(
            image=kokoro_image,
            voice=kokoro_voice,
            speed=kokoro_speed,
            sentence_silence=sentence_silence,
            cpus=cpus,
            docker_bin=docker_bin,
        )
    raise SpeechError(
        f"Unknown speech engine {engine!r}. Use 'kokoro', 'piper' or 'gtts'."
    )
