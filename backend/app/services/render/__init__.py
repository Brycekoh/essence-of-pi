from functools import lru_cache

from .base import RenderError, Renderer, RenderResult, RenderTimeout
from .manim_docker import ManimDockerRenderer
from .stub import StubRenderer

__all__ = [
    "Renderer",
    "RenderError",
    "RenderResult",
    "RenderTimeout",
    "ManimDockerRenderer",
    "StubRenderer",
    "build_renderer",
]


@lru_cache
def build_renderer(image: str, quality: str, memory: str, cpus: str, docker_bin: str) -> Renderer:
    """Cached on its arguments, for the same reasons as `build_llm`."""
    return ManimDockerRenderer(
        image=image, quality=quality, memory=memory, cpus=cpus, docker_bin=docker_bin
    )
