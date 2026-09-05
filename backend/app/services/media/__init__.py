from functools import lru_cache

from .base import MediaError, MediaTimeout, MediaTool
from .ffmpeg import FfmpegMedia
from .stub import StubMedia

__all__ = [
    "MediaTool",
    "MediaError",
    "MediaTimeout",
    "FfmpegMedia",
    "StubMedia",
    "build_media",
]


@lru_cache
def build_media(image: str, memory: str, cpus: str, docker_bin: str) -> MediaTool:
    return FfmpegMedia(image=image, memory=memory, cpus=cpus, docker_bin=docker_bin)
