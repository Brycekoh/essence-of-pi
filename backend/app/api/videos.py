from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..scenes import build_scene
from ..services.render import RenderError, RenderTimeout, build_renderer
from ..services.render.base import Renderer
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
    scene_name: str
    seconds: float


def provide_renderer(settings: Settings = Depends(get_settings)) -> Renderer:
    """The renderer dependency. Tests override this with a stub."""
    return build_renderer(
        settings.renderer_image,
        settings.render_quality,
        settings.render_memory,
        settings.render_cpus,
        settings.renderer_docker_bin,
    )


@router.post("", response_model=RenderResponse, status_code=status.HTTP_201_CREATED)
async def render_concept_video(
    paper_id: str,
    concept_id: str,
    settings: Settings = Depends(get_settings),
    store: PaperStore = Depends(get_store),
    renderer: Renderer = Depends(provide_renderer),
) -> RenderResponse:
    """Render this concept's title card and store the mp4.

    This blocks the request for the length of the render -- tens of seconds at
    `-qm`. That is a known and deliberate milestone-3 shortcut: the point here
    is to learn the render pipeline, and milestone 6 moves it onto a queue.
    """
    try:
        concept = store.concept(paper_id, concept_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")
    except ConceptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such concept.")

    code, scene_name = build_scene(concept)
    destination = store.video_path(concept_id)

    try:
        result = await renderer.render(
            code=code,
            scene_name=scene_name,
            destination=destination,
            timeout=settings.render_timeout_seconds,
        )
    except RenderTimeout as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, str(exc)) from exc
    except RenderError as exc:
        # The stderr is not returned to the client -- it can name host paths.
        # From milestone 4 it becomes the model's correction prompt instead.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    url = f"/api/papers/{paper_id}/concepts/{concept_id}/video"
    store.set_video(paper_id, concept_id, url)
    return RenderResponse(
        concept_id=concept_id,
        video_url=url,
        scene_name=result.scene_name,
        seconds=round(result.seconds, 2),
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
