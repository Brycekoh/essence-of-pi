"""Generate a Manim scene with an LLM, render it, and correct it when it fails.

The loop is the milestone:

    ask for code -> check it statically -> render it in the sandbox
                 -> on failure, hand the model its own code and the error
                 -> repeat, up to N attempts

Two cheap ideas do most of the work. First, a static `compile()`/AST pass
rejects code that cannot possibly render before paying for a container start.
Second, the *error text itself* is the correction prompt -- the model is far
better at fixing a concrete traceback than at avoiding the mistake in advance.

If every attempt fails, the hand-written title card from milestone 3 is
rendered instead, so a user always gets something back. That fallback is the
reason milestone 3 built the template first.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..models import Concept, ManimScene, RenderAttempt
from ..scenes import build_scene as build_title_card
from . import codecheck
from .llm.base import LLMClient, LLMError
from .render.base import Renderer, RenderError, RenderResult, RenderTimeout

SCENE_NAME = "ConceptScene"

SYSTEM = f"""\
You write Manim Community v0.19 scenes in the visual idiom of 3blue1brown: \
dark background, few elements on screen at once, one idea developed at a time, \
motion that carries meaning rather than decoration.

House rules, all of them hard requirements:

- Output complete Python starting with `from manim import *`.
- Define exactly one class, `{SCENE_NAME}(Scene)`, with a `construct(self)` method.
- Import nothing else except numpy or the standard `math` module.
- No file access, no network, no shelling out. There is no filesystem to use \
and no internet to reach.
- No external assets: no SVGImageMobject, ImageMobject, or anything loaded \
from disk. Build everything from primitives.
- Use `Text` for prose. Use `MathTex` only for actual mathematics, and keep \
the LaTeX simple -- it is the most common cause of a failed render.
- Keep the whole animation between 10 and 25 seconds.
- Prefer `self.play(...)` with explicit `run_time`, and end with `self.wait(1.5)`.
- Position things relative to each other (`next_to`, `to_edge`, `shift`) rather \
than with absolute coordinates, and keep everything inside the frame.\
"""

GENERATE = """\
Animate this concept from a research paper.

Name: {name}
Summary: {summary}
Explanation: {explanation}
What the animation should show: {visual_hint}

Show the mechanism, not a list of bullet points. If the concept is a process, \
animate the steps in order. If it is a relationship, show the two things and \
what connects them.\
"""

CORRECT = """\
The code below failed. Fix it and return the complete corrected scene.

The error:
{error}

The code that produced it:
{code}

Change what the error points at. Keep everything that was working, and do not \
start over with a different animation unless the error makes that unavoidable.\
"""

# Manim's output is rich-formatted and enormous. Measured on a real failure:
# 3,455 characters of stderr, of which the one line that named the mistake was
# the last. Most of the rest was box-drawing frames around manim's own source.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_BOX = "│┃┏┐┓└┗┛║╔╗╚╝─━═╭╮╯╰╌╡╨┤├┬┴┼"
_POINTER = "❱"  # rich's "this is the failing line" marker
_ERROR_BUDGET = 1_800


@dataclass
class AnimationOutcome:
    result: Optional[RenderResult]
    attempts: list[RenderAttempt] = field(default_factory=list)
    generated: bool = False  # False when the title-card fallback was used
    plan: str = ""


def distil_error(text: str, budget: int = _ERROR_BUDGET) -> str:
    """Reduce manim's output to something worth spending tokens on.

    Three passes, each one earned by looking at a real failure:

    1. Strip ANSI escapes.
    2. Strip rich's box-drawing frames. A boxed traceback spends most of its
       characters on borders and on manim's own source, neither of which helps
       the model fix *its* code.
    3. Lead with the final exception line, then as much trailing context as the
       budget allows -- so the one line that names the mistake can never be the
       thing truncation throws away.
    """
    clean = _ANSI.sub("", text)

    lines: list[str] = []
    for raw in clean.splitlines():
        if not raw.strip(_BOX + " \t"):
            continue  # a horizontal rule, or an empty boxed line
        line = "".join(" " if ch in _BOX else ch for ch in raw)
        line = line.replace(_POINTER, ">").rstrip()
        if line.strip():
            lines.append(line.strip() if line.strip().startswith(">") else line)

    if not lines:
        return "The renderer produced no error output."

    body = "\n".join(lines)
    if len(body) <= budget:
        return body

    headline = lines[-1].strip()
    room = budget - len(headline) - 5
    return f"{headline}\n...\n{body[-room:]}" if room > 0 else headline[:budget]


async def animate_concept(
    llm: LLMClient,
    renderer: Renderer,
    concept: Concept,
    destination: Path,
    *,
    max_attempts: int = 3,
    timeout: float = 300.0,
    fallback: bool = True,
) -> AnimationOutcome:
    """Run the generate-render-correct loop for one concept."""
    outcome = AnimationOutcome(result=None)
    previous_code: Optional[str] = None
    previous_error: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        prompt = (
            CORRECT.format(error=previous_error, code=previous_code)
            if previous_error
            else GENERATE.format(
                name=concept.name,
                summary=concept.summary,
                explanation=concept.explanation,
                visual_hint=concept.visual_hint,
            )
        )

        try:
            scene = await llm.structured(
                prompt=prompt,
                schema=ManimScene,
                system=SYSTEM,
                # Slightly warmer on the first pass, colder when correcting:
                # a fix should be conservative, not creative.
                temperature=0.6 if previous_error is None else 0.1,
            )
        except LLMError as exc:
            outcome.attempts.append(
                RenderAttempt(attempt=attempt, outcome="llm-failed", detail=str(exc))
            )
            break

        outcome.plan = scene.plan
        code = _strip_fences(scene.code)

        try:
            report = codecheck.check(code, SCENE_NAME)
        except codecheck.CodeRejected as exc:
            # Rejected without starting a container -- microseconds, not seconds.
            outcome.attempts.append(
                RenderAttempt(attempt=attempt, outcome="invalid-code", detail=str(exc))
            )
            previous_code, previous_error = code, str(exc)
            continue

        try:
            result = await renderer.render(
                code=code,
                scene_name=SCENE_NAME,
                destination=destination,
                timeout=timeout,
            )
        except RenderTimeout:
            detail = (
                f"The render exceeded {timeout:.0f} seconds. Make the animation "
                "shorter and simpler: fewer mobjects, fewer simultaneous "
                "animations, shorter run_times."
            )
            outcome.attempts.append(
                RenderAttempt(attempt=attempt, outcome="timeout", detail=detail)
            )
            previous_code, previous_error = code, detail
            continue
        except RenderError as exc:
            detail = distil_error(exc.stderr or str(exc))
            outcome.attempts.append(
                RenderAttempt(attempt=attempt, outcome="render-failed", detail=detail)
            )
            previous_code, previous_error = code, detail
            continue

        outcome.attempts.append(
            RenderAttempt(
                attempt=attempt,
                outcome="rendered",
                detail="; ".join(report.warnings),
            )
        )
        outcome.result = result
        outcome.generated = True
        return outcome

    if fallback:
        outcome.result = await _render_title_card(renderer, concept, destination, timeout)
    return outcome


async def _render_title_card(
    renderer: Renderer, concept: Concept, destination: Path, timeout: float
) -> Optional[RenderResult]:
    """Last resort: the hand-written card from milestone 3.

    It has rendered thousands of times without failing, which is exactly what a
    fallback needs to be.
    """
    code, scene_name = build_title_card(concept)
    try:
        return await renderer.render(
            code=code, scene_name=scene_name, destination=destination, timeout=timeout
        )
    except RenderError:
        return None


def _strip_fences(code: str) -> str:
    """Belt and braces.

    `response_schema` means the model returns a JSON string field rather than a
    markdown document, so fences should never appear. They occasionally do
    anyway -- the model writes them *inside* the string. Cheap to remove, and
    the alternative is a guaranteed syntax error.
    """
    text = code.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
