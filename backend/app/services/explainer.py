"""Turn one concept into a narrated, multi-scene explainer.

The order of operations is the whole point of this module:

    split into scenes  ->  speak each scene  ->  MEASURE the speech
                       ->  animate to that measured length
                       ->  mux  ->  concatenate

Narration is synthesised *before* any animation code is written, so the scene
is built to fit the words. Milestone 5 part 1 did it the other way round and
measured the result: 5.3 seconds of animation under 13.7 seconds of speech,
which meant holding a dead frame for eight seconds. Padding is the safety net,
not the plan.

A scene that cannot be animated is skipped rather than sinking the video --
the same instinct as the title-card fallback, one level up.
"""

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..models import Concept, SceneSpec, SceneSplit
from ..models.job import JobEvent
from .animation import AnimationOutcome, SceneBrief, animate
from .llm.base import LLMClient, LLMError
from .media.base import MediaError, MediaTool
from .speech.base import Speech, SpeechError

SPLIT_SYSTEM = """\
You plan short explainer videos in the style of 3blue1brown. You take one idea \
and lay out the smallest sequence of scenes that makes it click.

How a good sequence works: the first scene sets up the question or the problem, \
the middle scenes develop the mechanism one step at a time, and the last scene \
lands the idea. Each scene shows one thing. Nothing is repeated.

The narration is spoken aloud, so write it to be heard: plain sentences, no \
bullet points, no "in this video", no reading formulas out symbol by symbol.\
"""

SPLIT_PROMPT = """\
Break this concept into {max_scenes} scenes or fewer.

Name: {name}
Summary: {summary}
Explanation: {explanation}
What an animation should show: {visual_hint}

Fewer scenes is better than padding. If the idea genuinely takes one scene, \
give one scene.\
"""


@dataclass
class SceneOutcome:
    index: int
    narration: str
    audio_seconds: Optional[float]
    animation: Optional[AnimationOutcome]
    clip: Optional[Path]
    note: str = ""

    @property
    def generated(self) -> bool:
        return bool(self.animation and self.animation.generated)


@dataclass
class ExplainerOutcome:
    path: Optional[Path]
    scenes: list[SceneOutcome] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def generated_scenes(self) -> int:
        return sum(1 for s in self.scenes if s.generated)

    @property
    def rendered_scenes(self) -> int:
        return sum(1 for s in self.scenes if s.clip)


async def build_explainer(
    llm: LLMClient,
    renderer,
    speech: Speech,
    media: MediaTool,
    concept: Concept,
    destination: Path,
    *,
    workdir: Path,
    max_scenes: int = 3,
    max_attempts: int = 3,
    timeout: float = 300.0,
    progress=None,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> ExplainerOutcome:
    """Produce one narrated explainer for `concept`.

    `progress` is called with a `JobEvent` at each stage. It knows nothing
    about jobs or HTTP -- it is just somewhere to report to, which is what
    keeps this module free of either.

    `semaphore` bounds how many scenes render at once, across every job in the
    process. Scenes are independent once their narration is measured, so they
    animate in parallel; without a bound, three jobs of three scenes would ask
    the machine for nine containers.
    """
    def emit(stage: str, message: str, scene=None, total=None) -> None:
        if progress:
            progress(
                JobEvent(stage=stage, message=message, scene=scene, total_scenes=total)
            )

    workdir.mkdir(parents=True, exist_ok=True)
    emit("split", f"Breaking '{concept.name}' into scenes.")

    try:
        split = await llm.structured(
            prompt=SPLIT_PROMPT.format(
                max_scenes=max_scenes,
                name=concept.name,
                summary=concept.summary,
                explanation=concept.explanation,
                visual_hint=concept.visual_hint,
            ),
            schema=SceneSplit,
            system=SPLIT_SYSTEM,
            temperature=0.4,
        )
    except LLMError as exc:
        # Without a split there is nothing to build. One scene from the concept
        # itself would cost more quota to produce something worse.
        return ExplainerOutcome(
            path=None,
            scenes=[
                SceneOutcome(
                    index=1,
                    narration="",
                    audio_seconds=None,
                    animation=None,
                    clip=None,
                    note=f"could not split the concept: {exc}",
                )
            ],
        )

    specs = [s for s in split.scenes if s.narration.strip()][:max_scenes]
    if not specs:
        return ExplainerOutcome(path=None)

    emit("narrate", f"Narrating {len(specs)} scenes.", total=len(specs))

    # Narration first, for every scene, before any animation is generated:
    # each scene's length is a measured fact by the time its code is written.
    narrations = await _narrate_all(speech, media, specs, workdir)

    async def one(index: int, spec: SceneSpec, narration) -> SceneOutcome:
        audio, seconds, note = narration
        # The semaphore is held for the whole generate-render cycle, not just
        # the render: the model call is what decides how long the container
        # will run, and releasing between them just lets everything pile up.
        async with (semaphore or contextlib.nullcontext()):
            emit(
                "animate",
                f"Animating scene {index} of {len(specs)}.",
                scene=index,
                total=len(specs),
            )
            return await _build_scene(
                llm,
                renderer,
                media,
                concept,
                spec,
                index=index,
                audio=audio,
                seconds=seconds,
                note=note,
                workdir=workdir,
                max_attempts=max_attempts,
                timeout=timeout,
            )

    outcomes = list(
        await asyncio.gather(
            *(
                one(i, spec, narration)
                for i, (spec, narration) in enumerate(zip(specs, narrations), start=1)
            )
        )
    )

    clips = [s.clip for s in outcomes if s.clip]
    if not clips:
        return ExplainerOutcome(path=None, scenes=outcomes)

    emit("stitch", f"Stitching {len(clips)} clips together.", total=len(specs))
    try:
        await media.concat(clips, destination)
        seconds = await media.duration(destination)
    except MediaError:
        return ExplainerOutcome(path=None, scenes=outcomes)

    return ExplainerOutcome(path=destination, scenes=outcomes, seconds=seconds)


async def _narrate_all(
    speech: Speech, media: MediaTool, specs: list[SceneSpec], workdir: Path
) -> list[tuple[Optional[Path], Optional[float], str]]:
    """Synthesise every scene's narration concurrently, then measure each.

    Concurrent because TTS is network-bound and independent per scene; the
    animation that follows is the slow part and is not.
    """

    async def one(index: int, spec: SceneSpec):
        path = workdir / f"scene{index:02d}{speech.suffix}"
        try:
            await speech.say(spec.narration, path)
        except SpeechError as exc:
            return None, None, f"narration failed: {exc}"
        try:
            return path, await media.duration(path), ""
        except MediaError as exc:
            # The audio exists but cannot be measured, so the scene gets no
            # duration target. Better than dropping the narration entirely.
            return path, None, f"could not measure narration: {exc}"

    return list(
        await asyncio.gather(*(one(i, s) for i, s in enumerate(specs, start=1)))
    )


async def _build_scene(
    llm,
    renderer,
    media: MediaTool,
    concept: Concept,
    spec: SceneSpec,
    *,
    index: int,
    audio: Optional[Path],
    seconds: Optional[float],
    note: str,
    workdir: Path,
    max_attempts: int,
    timeout: float,
) -> SceneOutcome:
    silent = workdir / f"scene{index:02d}-silent.mp4"
    brief = SceneBrief(
        description="\n".join(
            [
                f"This is scene {index} of an explainer about: {concept.name}.",
                f"The narration spoken over it is: {spec.narration}",
                f"What to show: {spec.visual}",
            ]
        ),
        # A failed scene falls back to a card carrying its own narration, so
        # the video still says the right thing even when it cannot show it.
        fallback_title=concept.name,
        fallback_body=spec.narration,
        target_seconds=seconds,
    )

    animation = await animate(
        llm, renderer, brief, silent, max_attempts=max_attempts, timeout=timeout
    )
    if animation.result is None:
        return SceneOutcome(index, spec.narration, seconds, animation, None, note)

    if audio is None:
        return SceneOutcome(index, spec.narration, seconds, animation, silent, note)

    narrated = workdir / f"scene{index:02d}.mp4"
    try:
        await media.mux(silent, audio, narrated)
    except MediaError as exc:
        # Keep the silent clip rather than losing the scene.
        return SceneOutcome(
            index, spec.narration, seconds, animation, silent,
            f"{note} muxing failed: {exc}".strip(),
        )
    return SceneOutcome(index, spec.narration, seconds, animation, narrated, note)
