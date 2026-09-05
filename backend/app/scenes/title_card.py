"""The hand-written scene for milestone 3.

No model wrote this. That is the point: the render path gets built and debugged
against source we control, so that when milestone 4 swaps this function for an
LLM, every failure that follows is the model's, not the pipeline's.

Two things here outlive this milestone:

- `_literal()`. Concept text goes into generated Python *as a literal*, never
  interpolated into an expression, so a concept named `"); import os;
  os.system("` is inert data rather than code. Milestone 4 keeps this even
  though the model writes the surrounding code.
- Plain `Text`, not `MathTex`. Text goes through Pango and accepts anything;
  LaTeX chokes on stray `%`, `&`, `_` and `$`, which paper titles are full of.
"""

import textwrap

from ..models import Concept

SCENE_NAME = "ConceptCard"

_TEMPLATE = '''\
from manim import *


class ConceptCard(Scene):
    def construct(self):
        self.camera.background_color = "#0e1116"

        title = Text({title}, font_size=44, color="#58c4dd", weight=BOLD)
        rule = Line(LEFT, RIGHT, color="#3a6a7a", stroke_width=3)
        rule.set_width(max(title.width + 0.8, 3.0))
        body = Paragraph(
            *{body_lines},
            alignment="center",
            font_size=24,
            line_spacing=0.9,
            color="#d7dce2",
        )

        title.to_edge(UP, buff=1.6)
        rule.next_to(title, DOWN, buff=0.35)
        body.next_to(rule, DOWN, buff=0.7)
        VGroup(title, rule, body).move_to(ORIGIN)

        self.play(Write(title), run_time=1.4)
        self.play(Create(rule), run_time=0.5)
        self.play(FadeIn(body, shift=UP * 0.3), run_time=1.4)
        self.wait(2)
'''


def _literal(value: object) -> str:
    """Return `value` as a Python literal, escaped so it cannot become code.

    `repr`, not `json.dumps`. JSON string syntax looks like a subset of
    Python's, but `json.dumps` escapes astral-plane characters as UTF-16
    surrogate pairs -- so an emoji round-trips through Python as two lone
    surrogates rather than the character. `repr` is exact for every string.
    """
    return repr(value)


def _wrap(text: str, width: int = 52, max_lines: int = 5) -> list[str]:
    """Manim's Text does not wrap, so wrapping happens here."""
    lines = textwrap.wrap(" ".join(text.split()), width=width) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:") + "..."
    return lines


def build_scene(concept: Concept) -> tuple[str, str]:
    """Return (manim source, scene name) for a concept's title card."""
    title = " ".join(concept.name.split())[:60] or "Untitled concept"
    body = concept.summary.strip() or concept.explanation.strip()

    code = _TEMPLATE.format(
        title=_literal(title),
        body_lines=_literal(_wrap(body)),
    )
    return code, SCENE_NAME
