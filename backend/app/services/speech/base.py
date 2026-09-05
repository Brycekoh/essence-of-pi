"""The narration seam.

One method, so the voice can be swapped without touching anything upstream.
gTTS is what milestone 5 starts with because it needs no key; it is also
robotic, and the point of this interface is that replacing it later is a new
module rather than an edit.
"""

from pathlib import Path
from typing import Protocol


class SpeechError(RuntimeError):
    """Narration could not be synthesised."""


class Speech(Protocol):
    #: File extension the synthesiser produces, including the dot.
    suffix: str

    async def say(self, text: str, destination: Path) -> Path:
        """Write spoken `text` to `destination`. Raises `SpeechError`."""
        ...
