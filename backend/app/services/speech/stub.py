"""A `Speech` that writes a plausible file without touching the network."""

from pathlib import Path

from .base import SpeechError

# An ID3 header followed by silence-ish bytes: enough that anything sniffing
# the file sees an mp3 rather than text with the wrong extension.
_FAKE_MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" * 32


class StubSpeech:
    suffix = ".mp3"

    def __init__(self, error: Exception | None = None):
        self.error = error
        self.said: list[str] = []

    async def say(self, text: str, destination: Path) -> Path:
        if self.error:
            raise self.error
        cleaned = " ".join(text.split())
        if not cleaned:
            raise SpeechError("Nothing to say.")
        self.said.append(cleaned)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_FAKE_MP3)
        return destination
