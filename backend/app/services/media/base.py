"""The media seam: probe, mux, concatenate."""

from pathlib import Path
from typing import Protocol


class MediaError(RuntimeError):
    def __init__(self, message: str, stderr: str = ""):
        super().__init__(message)
        self.stderr = stderr


class MediaTimeout(MediaError):
    """The operation outlived its timeout."""


class MediaTool(Protocol):
    async def duration(self, path: Path) -> float:
        """Length in seconds of an audio or video file."""
        ...

    async def mux(self, video: Path, audio: Path, destination: Path) -> Path:
        """Put `audio` onto `video`, holding the last frame if audio is longer."""
        ...

    async def concat(self, clips: list[Path], destination: Path) -> Path:
        """Join clips end to end, in order."""
        ...
