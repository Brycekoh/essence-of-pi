from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..services.explainer import build_explainer
from ..services.llm.base import LLMClient
from ..services.media.base import MediaTool
from ..services.render.base import Renderer
from ..services.speech.base import Speech
from ..services.store import (
    ConceptNotFoundError,
    PaperNotFoundError,
    PaperStore,
    get_store,
)
from .deps import provide_llm, provide_media, provide_renderer, provide_speech

router = APIRouter(prefix="/papers/{paper_id}/concepts/{concept_id}/video", tags=["video"])


class SceneReport(BaseModel):
    """What happened to one scene, so a caller can see inside the pipeline.

    `attempts` carries the *outcomes* only -- "render-failed", "invalid-code"
    -- and never the detail behind them. That detail is distilled renderer
    stderr, which names paths inside the image and, on a bad day, could name
    paths outside it. It is written for the model and for the server log, not
    for an HTTP client. This leaked briefly in milestone 4 when the attempt
    objects were serialised whole into a 502 body; there is a test for it now.
    """

    index: int
    narration: str
    seconds: Optional[float]  # measured narration length, which set the target
    generated: bool           # False when this scene fell back to a card
    attempts: list[str]
    note: str = ""


class VideoResponse(BaseModel):
    concept_id: str
    video_url: str
    seconds: float
    scenes: list[SceneReport]
    generated_scenes: int  # how many were animated rather than carded


@router.post("", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def render_concept_video(
    paper_id: str,
    concept_id: str,
    settings: Settings = Depends(get_settings),
    store: PaperStore = Depends(get_store),
    renderer: Renderer = Depends(provide_renderer),
    llm: LLMClient = Depends(provide_llm),
    speech: Speech = Depends(provide_speech),
    media: MediaTool = Depends(provide_media),
) -> VideoResponse:
    """Build a narrated explainer for this concept.

    Split into scenes, narrate each, measure the narration, animate to that
    length, mux and concatenate.

    Still blocking, and now the slowest thing in the app: one model call to
    split, then up to `max_render_attempts` calls and container starts per
    scene. Milestone 6 moves this onto a queue -- by this milestone that is
    less a nicety than the obvious next problem.
    """
    try:
        concept = store.concept(paper_id, concept_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")
    except ConceptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such concept.")

    destination = store.video_path(concept_id)
    outcome = await build_explainer(
        llm,
        renderer,
        speech,
        media,
        concept,
        destination,
        workdir=destination.parent / f".scenes-{concept_id}",
        max_scenes=settings.max_scenes,
        max_attempts=settings.max_render_attempts,
        timeout=settings.render_timeout_seconds,
    )

    scenes = [
        SceneReport(
            index=s.index,
            narration=s.narration,
            seconds=s.audio_seconds,
            generated=s.generated,
            attempts=[a.outcome for a in s.animation.attempts] if s.animation else [],
            note=s.note,
        )
        for s in outcome.scenes
    ]

    if outcome.path is None:
        # The scene reports are our own diagnostics, not raw renderer stderr,
        # so they are safe to hand back.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            {
                "message": "Could not build a video for this concept.",
                "scenes": [s.model_dump() for s in scenes],
            },
        )

    url = f"/api/papers/{paper_id}/concepts/{concept_id}/video"
    store.set_video(paper_id, concept_id, url)
    return VideoResponse(
        concept_id=concept_id,
        video_url=url,
        seconds=round(outcome.seconds, 2),
        scenes=scenes,
        generated_scenes=outcome.generated_scenes,
    )


@router.get("")
async def get_concept_video(
    paper_id: str, concept_id: str, store: PaperStore = Depends(get_store)
):
    """Serve the rendered mp4, or 404 if this concept has not been rendered."""
    try:
        store.concept(paper_id, concept_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")
    except ConceptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such concept.")

    path = store.video_path(concept_id)
    if not path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Not rendered yet -- POST to this URL first.",
        )

    return FileResponse(path, media_type="video/mp4", filename=f"{concept_id}.mp4")
