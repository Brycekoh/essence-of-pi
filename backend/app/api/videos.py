from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..models import RenderAttempt
from ..services.animation import animate_concept
from ..services.llm.base import LLMClient
from ..services.render.base import Renderer
from .deps import provide_llm, provide_renderer
from ..services.store import (
    ConceptNotFoundError,
    PaperNotFoundError,
    PaperStore,
    get_store,
)

router = APIRouter(prefix="/papers/{paper_id}/concepts/{concept_id}/video", tags=["video"])


class RenderResponse(BaseModel):
    concept_id: str
    video_url: str
    seconds: float
    generated: bool  # False when every attempt failed and the card was used
    plan: str        # what the model said it was going to animate
    attempts: list[RenderAttempt]


@router.post("", response_model=RenderResponse, status_code=status.HTTP_201_CREATED)
async def render_concept_video(
    paper_id: str,
    concept_id: str,
    settings: Settings = Depends(get_settings),
    store: PaperStore = Depends(get_store),
    renderer: Renderer = Depends(provide_renderer),
    llm: LLMClient = Depends(provide_llm),
) -> RenderResponse:
    """Have the model write an animation for this concept, and render it.

    Still blocking, and now blocking for longer: up to `max_render_attempts`
    model calls and container starts. Milestone 6 moves this onto a queue.
    """
    try:
        concept = store.concept(paper_id, concept_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")
    except ConceptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such concept.")

    outcome = await animate_concept(
        llm,
        renderer,
        concept,
        store.video_path(concept_id),
        max_attempts=settings.max_render_attempts,
        timeout=settings.render_timeout_seconds,
        fallback=settings.fallback_to_title_card,
    )

    if outcome.result is None:
        # Every attempt failed and the fallback did too, or is switched off.
        # The attempt log goes in the response so the caller can see why --
        # it is our own diagnostics, not raw renderer stderr.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            {
                "message": f"Could not render this concept in "
                f"{settings.max_render_attempts} attempts.",
                "attempts": [a.model_dump() for a in outcome.attempts],
            },
        )

    url = f"/api/papers/{paper_id}/concepts/{concept_id}/video"
    store.set_video(paper_id, concept_id, url)
    return RenderResponse(
        concept_id=concept_id,
        video_url=url,
        seconds=round(outcome.result.seconds, 2),
        generated=outcome.generated,
        plan=outcome.plan,
        attempts=outcome.attempts,
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
