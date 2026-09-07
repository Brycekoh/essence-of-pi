from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse

from ..config import Settings, get_settings
from ..models.job import Job
from ..services.explainer import build_explainer
from ..services.jobs import JobRegistry, get_registry
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


@router.post("", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
async def start_video_job(
    paper_id: str,
    concept_id: str,
    response: Response,
    settings: Settings = Depends(get_settings),
    store: PaperStore = Depends(get_store),
    registry: JobRegistry = Depends(get_registry),
    renderer: Renderer = Depends(provide_renderer),
    llm: LLMClient = Depends(provide_llm),
    speech: Speech = Depends(provide_speech),
    media: MediaTool = Depends(provide_media),
) -> Job:
    """Queue a video build and return immediately.

    **202, not 201.** Building takes minutes -- a split call plus up to three
    model calls and container starts per scene. Until milestone 6 this endpoint
    held the connection open for all of it, which no proxy tolerates and no
    user should be asked to watch.

    Poll `GET /api/jobs/{id}`, or subscribe to `GET /api/jobs/{id}/events`.
    """
    try:
        concept = store.concept(paper_id, concept_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")
    except ConceptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such concept.")

    # Submitting the same concept twice while the first build runs would spend
    # a second helping of quota to produce the same file.
    existing = registry.find_active(concept_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    job = registry.create(paper_id, concept_id)
    destination = store.video_path(concept_id)

    async def work(progress) -> None:
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
            progress=progress,
            semaphore=registry.semaphore,
        )
        if outcome.path is None:
            notes = "; ".join(s.note for s in outcome.scenes if s.note)
            registry.fail(
                job.id,
                f"No scene could be built. {notes}".strip(),
            )
            return

        url = f"/api/papers/{paper_id}/concepts/{concept_id}/video"
        store.set_video(paper_id, concept_id, url)
        registry.succeed(job.id, url)

    return registry.submit(job, work)


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
