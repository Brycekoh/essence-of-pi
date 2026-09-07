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
from ..services.media import build_media
from ..services.media.base import MediaTool
from ..services.render import build_renderer
from ..services.render.base import Renderer
from ..services.speech import build_speech
from ..services.speech.base import Speech


def provide_llm(settings: Settings = Depends(get_settings)) -> LLMClient:
    """The LLM, or a 503 explaining exactly what to configure.

    Letting `build_llm` raise inside dependency resolution would surface as an
    opaque 500.
    """
    try:
        return build_llm(settings.gemini_api_key, settings.llm_models_csv)
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


def provide_speech(settings: Settings = Depends(get_settings)) -> Speech:
    """Narration. Neither engine needs a key, so nothing can fail here."""
    return build_speech(
        settings.speech_engine,
        image=settings.renderer_image,
        voice=settings.piper_voice,
        sentence_silence=settings.speech_sentence_silence,
        length_scale=settings.speech_length_scale,
        noise_scale=settings.speech_noise_scale,
        noise_w_scale=settings.speech_noise_w_scale,
        lang=settings.speech_lang,
        tld=settings.speech_tld,
        memory=settings.render_memory,
        cpus=settings.render_cpus,
        docker_bin=settings.renderer_docker_bin,
    )


def provide_media(settings: Settings = Depends(get_settings)) -> MediaTool:
    """ffmpeg, in the same image and the same sandbox as the renderer."""
    return build_media(
        settings.renderer_image,
        settings.render_memory,
        settings.render_cpus,
        settings.renderer_docker_bin,
    )
