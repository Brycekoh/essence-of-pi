"""A `MediaTool` that fakes the file operations, for tests without Docker."""

from pathlib import Path

from .base import MediaError

_FAKE_MP4 = bytes.fromhex("0000001c667479706d70343200000200") + b"eop-stub-media"


class StubMedia:
    def __init__(self, durations: dict[str, float] | None = None):
        # Keyed on filename, so a test can say "this narration is 9 seconds".
        self.durations = durations or {}
        self.default_duration = 5.0
        self.calls: list[tuple] = []
        self.error: Exception | None = None

    async def duration(self, path: Path) -> float:
        self.calls.append(("duration", path))
        if self.error:
            raise self.error
        return self.durations.get(path.name, self.default_duration)

    async def mux(self, video: Path, audio: Path, destination: Path) -> Path:
        self.calls.append(("mux", video, audio, destination))
        if self.error:
            raise self.error
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_FAKE_MP4)
        return destination

    async def concat(self, clips: list[Path], destination: Path) -> Path:
        self.calls.append(("concat", list(clips), destination))
        if self.error:
            raise self.error
        if not clips:
            raise MediaError("Nothing to concatenate.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_FAKE_MP4)
        return destination
