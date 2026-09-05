"""Render Manim scenes inside a container.

Why Docker rather than a local manim install:

1. The toolchain is genuinely painful -- manim, ffmpeg and a LaTeX
   distribution, none of which are pleasant on Windows.
2. From milestone 4 onward the code being executed is written by a language
   model. Running that on the host is not an option. Building the container
   boundary now, while the code is still ours and the failure modes are
   boring, means milestone 4 inherits a sandbox instead of inventing one.

The container gets no network, a memory ceiling and a CPU quota, and is killed
on timeout.
"""

import asyncio
import shutil
import time
import uuid
from pathlib import Path

from .base import RenderError, RenderResult, RenderTimeout

# Manim writes to <media_dir>/videos/<source stem>/<resolution>/<Scene>.mp4.
# The resolution directory name depends on the quality flag, so the output is
# located by globbing rather than by reconstructing that path.
_CONTAINER_WORKDIR = "/manim"


class ManimDockerRenderer:
    def __init__(
        self,
        *,
        image: str,
        quality: str = "-qm",
        memory: str = "2g",
        cpus: str = "2",
        docker_bin: str = "docker",
    ):
        self.image = image
        self.quality = quality
        self.memory = memory
        self.cpus = cpus
        self.docker_bin = docker_bin

    async def render(
        self,
        *,
        code: str,
        scene_name: str,
        destination: Path,
        timeout: float,
    ) -> RenderResult:
        workdir = destination.parent / f".render-{uuid.uuid4().hex}"
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "scene.py").write_text(code, encoding="utf-8")

        # Named so it can be killed on timeout. Killing the `docker run` client
        # process does NOT stop the container it started -- the daemon owns it.
        container = f"eop-render-{uuid.uuid4().hex[:12]}"
        argv = self.build_argv(workdir=workdir, container=container, scene_name=scene_name)

        started = time.monotonic()
        try:
            stdout, stderr, exit_code = await self._run(argv, container, timeout)
            seconds = time.monotonic() - started

            if exit_code != 0:
                raise RenderError(
                    f"manim exited with code {exit_code}",
                    stderr=stderr,
                    exit_code=exit_code,
                )

            produced = sorted(workdir.glob(f"media/videos/**/{scene_name}.mp4"))
            if not produced:
                # manim can exit 0 having rendered nothing -- e.g. a Scene
                # whose construct() body is empty.
                raise RenderError(
                    f"manim reported success but produced no {scene_name}.mp4",
                    stderr=stderr,
                    exit_code=exit_code,
                )

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(produced[0]), destination)
            return RenderResult(
                path=destination,
                scene_name=scene_name,
                seconds=seconds,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def build_argv(self, *, workdir: Path, container: str, scene_name: str) -> list[str]:
        """The exact command line. Split out so the sandbox flags are testable.

        Every flag between `--name` and the image is load-bearing from
        milestone 4 onward, when the code inside `workdir` is model-written.
        """
        return [
            self.docker_bin, "run", "--rm",
            "--name", container,
            "--network", "none",           # generated code gets no internet
            "--memory", self.memory,
            "--cpus", self.cpus,
            "--volume", f"{workdir}:{_CONTAINER_WORKDIR}",
            self.image,
            "manim", self.quality, "--format=mp4",
            "--media_dir", f"{_CONTAINER_WORKDIR}/media",
            "scene.py", scene_name,
        ]

    async def _run(
        self, argv: list[str], container: str, timeout: float
    ) -> tuple[str, str, int]:
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RenderError(
                f"`{self.docker_bin}` is not on PATH. Install Docker Desktop, "
                "or point RENDERER_DOCKER_BIN at the binary."
            ) from exc

        try:
            out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await self._kill_container(container)
            process.kill()
            await process.wait()
            raise RenderTimeout(
                f"Render exceeded {timeout:.0f}s and was killed.",
                stderr="",
            )

        stderr = err.decode("utf-8", "replace")
        if process.returncode != 0 and "Cannot connect to the Docker daemon" in stderr:
            raise RenderError(
                "The Docker daemon is not running. Start Docker Desktop and retry.",
                stderr=stderr,
                exit_code=process.returncode,
            )

        return out.decode("utf-8", "replace"), stderr, process.returncode or 0

    async def _kill_container(self, container: str) -> None:
        """Stop the container the timed-out client left behind."""
        try:
            killer = await asyncio.create_subprocess_exec(
                self.docker_bin, "kill", container,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(killer.wait(), timeout=15)
        except (OSError, asyncio.TimeoutError):
            # Best effort. `--rm` cleans up whenever it does exit.
            pass
