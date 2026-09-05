"""Shared FastAPI dependencies.

These exist as named functions in one place for two reasons: several routers
need the same collaborator, and `dependency_overrides` is keyed on the function
object -- so a duplicated dependency means a test double that only takes effect
on half the routes.
"""

from fastapi import Depends, HTTPException, status

from ..config import Settings, get_settings
from ..services.llm import LLMNotConfigured, build_llm
from ..services.llm.base import LLMClient
from ..services.render import build_renderer
from ..services.render.base import Renderer


def provide_llm(settings: Settings = Depends(get_settings)) -> LLMClient:
    """The LLM, or a 503 explaining exactly what to configure.

    Letting `build_llm` raise inside dependency resolution would surface as an
    opaque 500.
    """
    try:
        return build_llm(settings.gemini_api_key, settings.llm_model)
    except LLMNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def provide_renderer(settings: Settings = Depends(get_settings)) -> Renderer:
    """The renderer. Tests override this with a stub, so no Docker is needed."""
    return build_renderer(
        settings.renderer_image,
        settings.render_quality,
        settings.render_memory,
        settings.render_cpus,
        settings.renderer_docker_bin,
    )
