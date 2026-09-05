"""The seam between this app and whatever actually renders a Manim scene.

Same idea as `services/llm/base.py`: one narrow method, so the thing behind it
can change without the app noticing. Milestone 3 renders source code we wrote
ourselves; milestone 4 renders source code a model wrote. The interface is
identical, which is the whole point -- by the time an LLM is writing the code,
the execution path has already been built and tested.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class RenderError(RuntimeError):
    """A render that did not produce a video.

    `stderr` is kept because milestone 4 feeds it straight back to the model as
    the correction prompt. Losing it would mean losing the self-correction loop.
    """

    def __init__(self, message: str, stderr: str = "", exit_code: int | None = None):
        super().__init__(message)
        self.stderr = stderr
        self.exit_code = exit_code


class RenderTimeout(RenderError):
    """The renderer ran longer than allowed and was killed."""


@dataclass(frozen=True)
class RenderResult:
    path: Path
    scene_name: str
    seconds: float
    stdout: str
    stderr: str


class Renderer(Protocol):
    async def render(
        self,
        *,
        code: str,
        scene_name: str,
        destination: Path,
        timeout: float,
    ) -> RenderResult:
        """Render `scene_name` from `code` and write an mp4 to `destination`.

        Raises `RenderError` (or `RenderTimeout`) on failure. Must never raise
        anything else -- callers rely on that to turn failures into a 502
        rather than a 500.
        """
        ...
