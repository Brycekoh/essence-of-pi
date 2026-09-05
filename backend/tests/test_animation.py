"""The generate-render-correct loop."""

import pytest

from app.models import Concept, ManimScene
from app.services.animation import SCENE_NAME, animate_concept, distil_error
from app.services.codecheck import CodeRejected, check
from app.services.llm import LLMError, StubLLM
from app.services.render import RenderError, RenderTimeout, StubRenderer

from .test_concepts import draft

GOOD = f"""\
from manim import *


class {SCENE_NAME}(Scene):
    def construct(self):
        self.play(Write(Text("hello")))
        self.wait(1.5)
"""


def concept() -> Concept:
    base = draft("Attention").model_dump()
    base.update(id="c1", paper_id="p1")
    return Concept(**base)


def scene(code: str = GOOD, plan: str = "A word appears.") -> ManimScene:
    return ManimScene(plan=plan, code=code)


async def run(llm, renderer, tmp_path, **kw):
    return await animate_concept(
        llm, renderer, concept(), tmp_path / "out.mp4", timeout=60, **kw
    )


# --- the happy path -------------------------------------------------------


async def test_first_attempt_renders(tmp_path):
    llm, renderer = StubLLM([scene()]), StubRenderer()

    outcome = await run(llm, renderer, tmp_path)

    assert outcome.generated is True
    assert outcome.plan == "A word appears."
    assert [a.outcome for a in outcome.attempts] == ["rendered"]
    assert len(renderer.calls) == 1


# --- correction -----------------------------------------------------------


async def test_render_failure_feeds_stderr_back_to_the_model(tmp_path):
    """The error text *is* the correction prompt. That is the milestone."""
    llm = StubLLM([scene(), scene()])
    renderer = StubRenderer()
    renderer.errors = [
        RenderError(
            "manim exited with code 1",
            stderr="AttributeError: Mobject has no attribute 'nudge'",
            exit_code=1,
        )
    ]

    outcome = await run(llm, renderer, tmp_path)

    assert outcome.generated is True
    assert [a.outcome for a in outcome.attempts] == ["render-failed", "rendered"]

    second_prompt = llm.calls[1]["prompt"]
    assert "nudge" in second_prompt, "the model must see the actual error"
    assert GOOD.strip() in second_prompt, "and the code that produced it"


async def test_correction_runs_colder_than_generation(tmp_path):
    """A fix should be conservative; a first draft can be creative."""
    llm = StubLLM([scene(), scene()])
    renderer = StubRenderer()
    renderer.errors = [RenderError("boom", stderr="boom")]

    await run(llm, renderer, tmp_path)

    assert llm.calls[0]["temperature"] > llm.calls[1]["temperature"]


async def test_invalid_code_is_rejected_without_starting_a_container(tmp_path):
    """A syntax error costs microseconds, not a container start."""
    llm = StubLLM([scene(code="from manim import *\nclass Broken(Scene:"), scene()])
    renderer = StubRenderer()

    outcome = await run(llm, renderer, tmp_path)

    assert [a.outcome for a in outcome.attempts] == ["invalid-code", "rendered"]
    assert len(renderer.calls) == 1, "the broken code never reached the renderer"
    assert "syntax error" in llm.calls[1]["prompt"].lower()


async def test_timeout_tells_the_model_to_simplify(tmp_path):
    llm = StubLLM([scene(), scene()])
    renderer = StubRenderer()
    renderer.errors = [RenderTimeout("too slow")]

    outcome = await run(llm, renderer, tmp_path)

    assert [a.outcome for a in outcome.attempts] == ["timeout", "rendered"]
    assert "shorter and simpler" in llm.calls[1]["prompt"]


# --- giving up ------------------------------------------------------------


async def test_falls_back_to_the_title_card(tmp_path):
    """Three failures, then the hand-written card, so the caller gets a video."""
    llm = StubLLM([scene(), scene(), scene()])
    renderer = StubRenderer()
    renderer.errors = [RenderError("boom", stderr="boom")] * 3

    outcome = await run(llm, renderer, tmp_path, max_attempts=3)

    assert outcome.generated is False, "the caller must know this is the fallback"
    assert outcome.result is not None
    assert len(outcome.attempts) == 3
    assert renderer.calls[-1]["scene_name"] == "ConceptCard"


async def test_fallback_can_be_switched_off(tmp_path):
    llm = StubLLM([scene()])
    renderer = StubRenderer(error=RenderError("boom", stderr="boom"))

    outcome = await run(llm, renderer, tmp_path, max_attempts=1, fallback=False)

    assert outcome.result is None
    assert outcome.generated is False


async def test_llm_failure_stops_the_loop_immediately(tmp_path):
    """Retrying a dead provider three times just wastes three timeouts."""
    llm = StubLLM([LLMError("Gemini unavailable")])
    renderer = StubRenderer()

    outcome = await run(llm, renderer, tmp_path, max_attempts=3, fallback=False)

    assert [a.outcome for a in outcome.attempts] == ["llm-failed"]
    assert len(llm.calls) == 1


# --- error distillation ---------------------------------------------------


def test_distil_error_strips_ansi_and_keeps_the_tail():
    noisy = "\x1b[32mprogress\x1b[0m\n" * 500 + "AttributeError: no attribute 'nudge'"

    distilled = distil_error(noisy, budget=200)

    assert "\x1b[" not in distilled
    assert "nudge" in distilled, "the traceback is at the end, so keep the end"
    assert len(distilled) <= 200


def test_distil_error_leads_with_the_exception_when_truncating():
    """Truncation must never be what removes the line naming the mistake."""
    noisy = "filler line\n" * 500 + "AttributeError: Text object has no attribute 'nudge'"

    distilled = distil_error(noisy, budget=300)

    assert distilled.startswith("AttributeError: Text object has no attribute")
    assert len(distilled) <= 300


def test_distil_error_strips_rich_box_drawing():
    """Measured on real manim output: the frames were most of the payload."""
    boxed = (
        "╭─── Traceback ───╮\n"
        "│  4 class ConceptScene(Scene):    │\n"
        "│ ❱ 7     t.nudge(UP)             │\n"
        "╰──────────────╯\n"
        "AttributeError: Text object has no attribute 'nudge'"
    )

    distilled = distil_error(boxed)

    assert not set(distilled) & set("│╭╮╯╰─")
    assert "> 7     t.nudge(UP)" in distilled
    assert distilled.endswith("no attribute 'nudge'")


def test_distil_error_handles_silence():
    assert "no error output" in distil_error("   ")


# --- static checks --------------------------------------------------------


def test_check_accepts_good_code():
    report = check(GOOD, SCENE_NAME)
    assert report.scene_names == [SCENE_NAME]
    assert report.warnings == []


@pytest.mark.parametrize(
    "code, expected",
    [
        ("from manim import *\nx = (", "syntax error"),
        ("from manim import *\nx = 1", "No Scene subclass"),
        (
            "from manim import *\nclass Wrong(Scene):\n    def construct(self): pass",
            "must be named",
        ),
        (f"from manim import *\nclass {SCENE_NAME}(Scene):\n    pass", "no construct"),
        (
            "import requests\nfrom manim import *\n"
            f"class {SCENE_NAME}(Scene):\n    def construct(self): pass",
            "imports `requests`",
        ),
    ],
)
def test_check_rejects_with_an_actionable_message(code, expected):
    """Each message is written to be fed straight back to the model."""
    with pytest.raises(CodeRejected) as exc:
        check(code, SCENE_NAME)
    assert expected in str(exc.value)


def test_check_warns_about_filesystem_calls_without_rejecting():
    """A warning, not a rejection -- the container is the actual boundary."""
    code = (
        f"from manim import *\nclass {SCENE_NAME}(Scene):\n"
        "    def construct(self):\n        open('/etc/passwd')\n"
    )
    report = check(code, SCENE_NAME)
    assert any("open()" in w for w in report.warnings)


def test_check_rejects_two_scenes():
    code = (
        f"from manim import *\nclass {SCENE_NAME}(Scene):\n"
        "    def construct(self): pass\n"
        "class Other(Scene):\n    def construct(self): pass\n"
    )
    with pytest.raises(CodeRejected, match="Define exactly one"):
        check(code, SCENE_NAME)
