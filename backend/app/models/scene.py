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


class SceneSpec(BaseModel):
    """One beat of an explainer: what is said, and what is shown while it is said.

    `narration` is declared first deliberately. The spoken line is what fixes
    the scene's length -- it is synthesised and measured before any animation
    code is written, so the visual is built to fit the words rather than the
    words being padded to fit the visual.
    """

    narration: str = Field(
        ...,
        description=(
            "One to three sentences of spoken narration, in plain spoken "
            "English. No formulas read aloud symbol by symbol, no bullet "
            "points, no stage directions."
        ),
    )
    visual: str = Field(
        ...,
        description=(
            "What is on screen while that line is spoken: the objects, what "
            "moves, and what the viewer should notice. One or two sentences."
        ),
    )


class SceneSplit(BaseModel):
    """A concept broken into an ordered sequence of scenes."""

    scenes: list[SceneSpec]
