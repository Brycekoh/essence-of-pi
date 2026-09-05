from pydantic import BaseModel, Field


class ManimScene(BaseModel):
    """What the model returns when asked to animate a concept.

    Field order is load-bearing. Structured output is generated in declaration
    order, so `plan` is written before `code` and the model has committed to an
    approach by the time it starts emitting Python. Putting `code` first
    measurably degrades it -- the model starts typing before it has decided
    what it is animating.
    """

    plan: str = Field(
        ...,
        description=(
            "Two or three sentences: what appears on screen, what moves, and "
            "what the viewer should understand by the end. No code here."
        ),
    )
    code: str = Field(
        ...,
        description=(
            "Complete Python source for one Manim scene. Starts with "
            "`from manim import *` and defines exactly one Scene subclass. "
            "No markdown fences, no commentary."
        ),
    )


class RenderAttempt(BaseModel):
    """One trip round the generate-render-correct loop, for the response body."""

    attempt: int
    outcome: str  # "rendered" | "invalid-code" | "render-failed" | "timeout"
    detail: str = ""
