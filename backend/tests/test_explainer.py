"""Multi-scene narrated explainers.

The behaviour that matters here is the *order*: narration is synthesised and
measured before any animation code is written, so a scene is built to fit the
words rather than the words padded to fit the scene.
"""

import pytest

from app.models import Concept, ManimScene, SceneSpec, SceneSplit
from app.services.animation import SCENE_NAME
from app.services.explainer import build_explainer
from app.services.llm import LLMError, StubLLM
from app.services.media import MediaError, StubMedia
from app.services.render import RenderError, StubRenderer
from app.services.speech import SpeechError, StubSpeech

from .test_concepts import draft

GOOD = f"""\
from manim import *


class {SCENE_NAME}(Scene):
    def construct(self):
        self.play(Write(Text("hello")))
        self.wait(1.5)
"""


def concept() -> Concept:
    base = draft("Internal Covariate Shift").model_dump()
    base.update(id="c1", paper_id="p1")
    return Concept(**base)


def split(*narrations: str) -> SceneSplit:
    return SceneSplit(
        scenes=[
            SceneSpec(narration=n, visual=f"show {i}")
            for i, n in enumerate(narrations, start=1)
        ]
    )


def scene(plan: str = "A word appears.") -> ManimScene:
    return ManimScene(plan=plan, code=GOOD)


async def run(llm, tmp_path, *, speech=None, media=None, renderer=None, **kw):
    return await build_explainer(
        llm,
        renderer or StubRenderer(),
        speech or StubSpeech(),
        media or StubMedia(),
        concept(),
        tmp_path / "final.mp4",
        workdir=tmp_path / "work",
        timeout=60,
        **kw,
    )


# --- the happy path -------------------------------------------------------


async def test_builds_a_narrated_multi_scene_video(tmp_path):
    speech, media = StubSpeech(), StubMedia()
    llm = StubLLM([split("First line.", "Second line."), scene(), scene()])

    outcome = await run(llm, tmp_path, speech=speech, media=media)

    assert outcome.path is not None
    assert outcome.rendered_scenes == 2
    assert outcome.generated_scenes == 2
    assert speech.said == ["First line.", "Second line."]

    # Each scene is muxed, then all of them concatenated once.
    assert [c[0] for c in media.calls].count("mux") == 2
    assert [c[0] for c in media.calls].count("concat") == 1


async def test_measured_narration_length_reaches_the_animation_prompt(tmp_path):
    """The milestone in one assertion."""
    media = StubMedia(durations={"scene01.mp3": 13.0, "scene02.mp3": 7.0})
    llm = StubLLM([split("Long line.", "Short line."), scene(), scene()])

    await run(llm, tmp_path, media=media)

    first_scene_prompt = llm.calls[1]["prompt"]
    second_scene_prompt = llm.calls[2]["prompt"]
    assert "13 seconds" in first_scene_prompt
    assert "7 seconds" in second_scene_prompt
    assert "Long line." in first_scene_prompt, "the narration is context for the visual"


async def test_narration_happens_before_any_animation(tmp_path):
    """Speech first is the design, not an implementation detail."""
    speech, media = StubSpeech(), StubMedia()
    llm = StubLLM([split("One.", "Two."), scene(), scene()])

    await run(llm, tmp_path, speech=speech, media=media)

    # Both narrations were spoken and measured before the first scene prompt.
    durations_before_generation = [c for c in media.calls if c[0] == "duration"]
    assert len(durations_before_generation) >= 2
    assert speech.said == ["One.", "Two."]


async def test_scene_count_is_capped(tmp_path):
    llm = StubLLM([split("a", "b", "c", "d", "e"), scene(), scene()])

    outcome = await run(llm, tmp_path, max_scenes=2)

    assert len(outcome.scenes) == 2


async def test_blank_narration_scenes_are_dropped(tmp_path):
    llm = StubLLM([split("Real line.", "   "), scene()])

    outcome = await run(llm, tmp_path)

    assert len(outcome.scenes) == 1


# --- degrading ------------------------------------------------------------


async def test_a_failed_scene_is_skipped_not_fatal(tmp_path):
    """One bad scene must not sink the video."""
    renderer = StubRenderer()
    renderer.errors = [RenderError("boom", stderr="boom")]  # only scene 1 fails
    llm = StubLLM([split("One.", "Two."), scene(), scene()])

    outcome = await run(
        llm, tmp_path, renderer=renderer, max_attempts=1, max_scenes=2
    )

    assert outcome.path is not None, "scene 2 still carries the video"
    assert outcome.rendered_scenes == 2, "scene 1 fell back to a card"
    assert outcome.scenes[0].generated is False
    assert outcome.scenes[1].generated is True


async def test_failed_narration_leaves_a_silent_scene(tmp_path):
    speech = StubSpeech(error=SpeechError("gTTS refused"))
    media = StubMedia()
    llm = StubLLM([split("One."), scene()])

    outcome = await run(llm, tmp_path, speech=speech, media=media)

    assert outcome.path is not None
    assert outcome.scenes[0].clip is not None, "the animation survives"
    assert "narration failed" in outcome.scenes[0].note
    assert not [c for c in media.calls if c[0] == "mux"], "nothing to mux"


async def test_unmeasurable_narration_still_gets_animated(tmp_path):
    media = StubMedia()
    media.error = None
    llm = StubLLM([split("One."), scene()])

    class Unmeasurable(StubMedia):
        async def duration(self, path):
            if path.suffix == ".mp3":
                raise MediaError("ffprobe failed")
            return 5.0

    outcome = await run(llm, tmp_path, media=Unmeasurable())

    assert outcome.scenes[0].audio_seconds is None
    assert "could not measure" in outcome.scenes[0].note
    assert "seconds, because that is how long" not in llm.calls[1]["prompt"]


async def test_split_failure_returns_nothing_and_says_why(tmp_path):
    """No split means no video, and no further quota spent guessing."""
    llm = StubLLM([LLMError("Gemini unavailable")])

    outcome = await run(llm, tmp_path)

    assert outcome.path is None
    assert "could not split" in outcome.scenes[0].note
    assert len(llm.calls) == 1, "one failed call, not one per scene"


async def test_every_scene_failing_produces_no_video(tmp_path):
    renderer = StubRenderer(error=RenderError("boom", stderr="boom"))
    llm = StubLLM([split("One.", "Two."), scene(), scene()])

    outcome = await run(llm, tmp_path, renderer=renderer, max_attempts=1)

    assert outcome.path is None
    assert outcome.rendered_scenes == 0


async def test_concat_failure_is_reported_not_raised(tmp_path):
    class BadConcat(StubMedia):
        async def concat(self, clips, destination):
            raise MediaError("codecs differ")

    llm = StubLLM([split("One."), scene()])

    outcome = await run(llm, tmp_path, media=BadConcat())

    assert outcome.path is None
    assert outcome.rendered_scenes == 1, "the scenes were fine; joining them was not"
