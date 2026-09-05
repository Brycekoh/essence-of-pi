"""Narration via gTTS (Google Translate's voice).

No API key and no quota, which is why it is the starting point -- milestone 4
already showed how quickly a free quota disappears. It is an unofficial
endpoint, it needs network access from the backend process (not from the
render container, which has none), and it sounds like a satnav. All three are
acceptable for now and all three are reasons this sits behind `Speech`.
"""

import asyncio
from pathlib import Path

from .base import SpeechError


class GttsSpeech:
    suffix = ".mp3"

    def __init__(self, lang: str = "en", tld: str = "com", slow: bool = False):
        self.lang = lang
        self.tld = tld  # "co.uk", "com.au" etc. change the accent
        self.slow = slow

    async def say(self, text: str, destination: Path) -> Path:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise SpeechError("Nothing to say.")

        # gTTS is synchronous and does network I/O, so it goes to a thread for
        # the same reason pdfplumber does: an async def that blocks the loop is
        # worse than useless, it is misleading.
        return await asyncio.to_thread(self._write, cleaned, destination)

    def _write(self, text: str, destination: Path) -> Path:
        try:
            from gtts import gTTS
            from gtts.tts import gTTSError
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise SpeechError("gTTS is not installed (pip install gtts).") from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            gTTS(text=text, lang=self.lang, tld=self.tld, slow=self.slow).save(
                str(destination)
            )
        except gTTSError as exc:
            raise SpeechError(f"gTTS refused the request: {exc}") from exc
        except Exception as exc:
            raise SpeechError(f"Could not synthesise narration: {exc}") from exc

        if not destination.exists() or destination.stat().st_size == 0:
            raise SpeechError("gTTS produced an empty file.")
        return destination
