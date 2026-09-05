"""Audio and video operations, run through ffmpeg inside the render image.

Nothing media-related is installed on the host. The same image that renders
manim scenes carries ffmpeg (see `Dockerfile.render`), so probing, muxing and
concatenating all happen in the same sandbox as the rendering.

Every operation copies its inputs into a scratch directory, mounts that one
directory, and copies the result back -- a container gets exactly one mount,
and files scattered across the host are not reachable from inside it.
"""

import shutil
from pathlib import Path

from ..container import (
    CONTAINER_WORKDIR,
    ContainerError,
    ContainerTimeout,
    build_argv,
    container_name,
)
from ..container import run as run_container
from .base import MediaError, MediaTimeout


class FfmpegMedia:
    def __init__(
        self,
        *,
        image: str,
        memory: str = "1g",
        cpus: str = "2",
        docker_bin: str = "docker",
        timeout: float = 180.0,
    ):
        self.image = image
        self.memory = memory
        self.cpus = cpus
        self.docker_bin = docker_bin
        self.timeout = timeout

    # --- public API -------------------------------------------------------

    async def duration(self, path: Path) -> float:
        """Length of an audio or video file, in seconds."""
        with _scratch(path.parent) as work:
            shutil.copy2(path, work / path.name)
            stdout, stderr, code = await self._ffprobe(
                work,
                [
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    f"{CONTAINER_WORKDIR}/{path.name}",
                ],
            )
        if code != 0:
            raise MediaError(f"ffprobe failed on {path.name}", stderr=stderr)
        try:
            return float(stdout.strip().splitlines()[0])
        except (ValueError, IndexError) as exc:
            raise MediaError(
                f"ffprobe gave no duration for {path.name}: {stdout!r}", stderr=stderr
            ) from exc

    async def mux(self, video: Path, audio: Path, destination: Path) -> Path:
        """Put `audio` onto `video`.

        If the narration outlasts the animation the last frame is held rather
        than the audio being cut -- a sentence chopped mid-word is worse than a
        second of stillness. That path re-encodes; the common path copies the
        video stream untouched.
        """
        video_seconds = await self.duration(video)
        audio_seconds = await self.duration(audio)
        overhang = audio_seconds - video_seconds

        with _scratch(destination.parent) as work:
            shutil.copy2(video, work / "in.mp4")
            shutil.copy2(audio, work / f"in{audio.suffix}")

            command = [
                "-v", "error", "-y",
                "-i", f"{CONTAINER_WORKDIR}/in.mp4",
                "-i", f"{CONTAINER_WORKDIR}/in{audio.suffix}",
            ]
            if overhang > 0.05:
                command += [
                    "-vf", f"tpad=stop_mode=clone:stop_duration={overhang:.3f}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                ]
            else:
                command += ["-c:v", "copy", "-shortest"]
            command += ["-c:a", "aac", "-b:a", "128k", f"{CONTAINER_WORKDIR}/out.mp4"]

            _, stderr, code = await self._ffmpeg(work, command)
            if code != 0:
                raise MediaError("ffmpeg could not mux the audio", stderr=stderr)
            _deliver(work / "out.mp4", destination)
        return destination

    async def concat(self, clips: list[Path], destination: Path) -> Path:
        """Join clips end to end, in order.

        Uses the concat demuxer with stream copy, which is fast and lossless
        but requires the clips to share a codec and geometry. Everything here
        comes out of the same manim settings, so they do.
        """
        if not clips:
            raise MediaError("Nothing to concatenate.")
        if len(clips) == 1:
            shutil.copy2(clips[0], destination)
            return destination

        with _scratch(destination.parent) as work:
            names = []
            for index, clip in enumerate(clips):
                name = f"clip{index:03d}.mp4"
                shutil.copy2(clip, work / name)
                names.append(name)
            # `file 'x'` lines; the demuxer resolves them relative to the list.
            (work / "list.txt").write_text(
                "".join(f"file '{n}'\n" for n in names), encoding="utf-8"
            )

            _, stderr, code = await self._ffmpeg(
                work,
                [
                    "-v", "error", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", f"{CONTAINER_WORKDIR}/list.txt",
                    "-c", "copy",
                    f"{CONTAINER_WORKDIR}/out.mp4",
                ],
            )
            if code != 0:
                raise MediaError("ffmpeg could not concatenate the clips", stderr=stderr)
            _deliver(work / "out.mp4", destination)
        return destination

    # --- plumbing ---------------------------------------------------------

    async def _ffmpeg(self, work: Path, command: list[str]):
        return await self._run("ffmpeg", work, command)

    async def _ffprobe(self, work: Path, command: list[str]):
        return await self._run("ffprobe", work, command)

    async def _run(self, tool: str, work: Path, command: list[str]):
        name = container_name(f"eop-{tool}")
        argv = build_argv(
            image=self.image,
            command=command,
            workdir=work,
            container=name,
            memory=self.memory,
            cpus=self.cpus,
            docker_bin=self.docker_bin,
            entrypoint=tool,
        )
        try:
            return await run_container(
                argv, container=name, timeout=self.timeout, docker_bin=self.docker_bin
            )
        except ContainerTimeout as exc:
            raise MediaTimeout(str(exc)) from exc
        except ContainerError as exc:
            raise MediaError(str(exc), stderr=exc.stderr) from exc


class _scratch:
    """A temp directory beside the destination, removed on the way out.

    Beside, not in the system temp: the host path is bind-mounted into a
    container, and keeping it inside the project's storage avoids depending on
    which host directories Docker Desktop is allowed to share.
    """

    def __init__(self, near: Path):
        self.near = near

    def __enter__(self) -> Path:
        self.near.mkdir(parents=True, exist_ok=True)
        self.path = self.near / f".media-{container_name('')[1:]}"
        self.path.mkdir(parents=True, exist_ok=True)
        return self.path

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


def _deliver(produced: Path, destination: Path) -> None:
    if not produced.exists():
        raise MediaError(f"ffmpeg reported success but produced no {produced.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(produced), destination)
