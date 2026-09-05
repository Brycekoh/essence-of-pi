"""A `Renderer` that writes a placeholder file instead of running anything.

Keeps the test suite free of Docker, and lets the API be exercised on a machine
with no toolchain at all.
"""

import time
from pathlib import Path

from .base import RenderError, RenderResult

# The first bytes of a real MP4 (an ftyp box), so anything that sniffs the file
# sees a plausible video rather than a text file with the wrong extension.
_FAKE_MP4 = bytes.fromhex("0000001c667479706d70343200000200") + b"eop-stub-render"


class StubRenderer:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict] = []

    async def render(
        self, *, code: str, scene_name: str, destination: Path, timeout: float
    ) -> RenderResult:
        self.calls.append(
            {"code": code, "scene_name": scene_name, "destination": destination}
        )
        if self.error:
            raise self.error

        if f"class {scene_name}" not in code:
            # Cheap stand-in for the real failure: manim exits non-zero when
            # the scene it was asked for is not in the file.
            raise RenderError(
                f"No scene named {scene_name} in the source.",
                stderr=f"There are no scenes inside that module named {scene_name}",
                exit_code=1,
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_FAKE_MP4)
        return RenderResult(
            path=destination,
            scene_name=scene_name,
            seconds=0.0,
            stdout="",
            stderr="",
        )
