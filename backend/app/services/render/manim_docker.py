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

import shutil
import time
from pathlib import Path

from ..container import CONTAINER_WORKDIR, ContainerError, ContainerTimeout
from ..container import build_argv as build_container_argv
from ..container import container_name
from ..container import run as run_container
from .base import RenderError, RenderResult, RenderTimeout

# Manim writes to <media_dir>/videos/<source stem>/<resolution>/<Scene>.mp4.
# The resolution directory name depends on the quality flag, so the output is
# located by globbing rather than by reconstructing that path.


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
        workdir = destination.parent / f".render-{container_name('')[1:]}"
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "scene.py").write_text(code, encoding="utf-8")

        # Named so it can be killed on timeout. Killing the `docker run` client
        # process does NOT stop the container it started -- the daemon owns it.
        container = container_name("eop-render")
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
        return build_container_argv(
            image=self.image,
            command=[
                "manim", self.quality, "--format=mp4",
                "--media_dir", f"{CONTAINER_WORKDIR}/media",
                "scene.py", scene_name,
            ],
            workdir=workdir,
            container=container,
            memory=self.memory,
            cpus=self.cpus,
            docker_bin=self.docker_bin,
        )

    async def _run(
        self, argv: list[str], container: str, timeout: float
    ) -> tuple[str, str, int]:
        try:
            return await run_container(
                argv, container=container, timeout=timeout, docker_bin=self.docker_bin
            )
        except ContainerTimeout as exc:
            raise RenderTimeout(str(exc)) from exc
        except ContainerError as exc:
            raise RenderError(str(exc), stderr=exc.stderr, exit_code=exc.exit_code) from exc
