"""Running a command in a container, with a timeout that actually works.

Both things this app shells out to -- manim for rendering, ffmpeg for audio --
need the same three behaviours, so they live here once:

- no network, capped memory, capped CPU
- a *named* container, because killing the `docker run` client does not stop
  the container it started; the daemon owns it
- a clear error when the daemon simply is not running
"""

import asyncio
import random
import uuid
from pathlib import Path
from typing import Optional, Sequence

CONTAINER_WORKDIR = "/work"


class ContainerError(RuntimeError):
    """The command failed, or could not be started."""

    def __init__(self, message: str, stderr: str = "", exit_code: Optional[int] = None):
        super().__init__(message)
        self.stderr = stderr
        self.exit_code = exit_code


class ContainerTimeout(ContainerError):
    """The command outlived its timeout and the container was killed."""


def build_argv(
    *,
    image: str,
    command: Sequence[str],
    workdir: Path,
    container: str,
    memory: str = "2g",
    cpus: str = "2",
    docker_bin: str = "docker",
    entrypoint: Optional[str] = None,
) -> list[str]:
    """The exact command line, split out so the sandbox flags stay testable.

    Every flag between `--name` and the image is load-bearing: from milestone 4
    the code inside `workdir` is written by a language model.
    """
    argv = [
        docker_bin, "run", "--rm",
        "--name", container,
        "--network", "none",
        "--memory", memory,
        "--cpus", cpus,
        "--volume", f"{workdir}:{CONTAINER_WORKDIR}",
        # Make the mount the working directory. Without this the image's own
        # WORKDIR wins and relative paths like `scene.py` resolve somewhere
        # the mounted files are not.
        "--workdir", CONTAINER_WORKDIR,
    ]
    if entrypoint:
        argv += ["--entrypoint", entrypoint]
    argv.append(image)
    argv += list(command)
    return argv


def container_name(prefix: str = "eop") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def run(
    argv: Sequence[str],
    *,
    container: str,
    timeout: float,
    docker_bin: str = "docker",
) -> tuple[str, str, int]:
    """Run `argv`, returning (stdout, stderr, exit code).

    Raises `ContainerTimeout` if it overruns, `ContainerError` if docker itself
    cannot be reached. A non-zero exit code is returned, not raised -- callers
    know better than this module what a failure means.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ContainerError(
            f"`{docker_bin}` is not on PATH. Install Docker Desktop, or point "
            "RENDERER_DOCKER_BIN at the binary."
        ) from exc

    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _kill(container, docker_bin)
        process.kill()
        await process.wait()
        raise ContainerTimeout(f"Exceeded {timeout:.0f}s and was killed.")

    stderr = err.decode("utf-8", "replace")
    if process.returncode != 0 and "Cannot connect to the Docker daemon" in stderr:
        raise ContainerError(
            "The Docker daemon is not running. Start Docker Desktop and retry.",
            stderr=stderr,
            exit_code=process.returncode,
        )

    return out.decode("utf-8", "replace"), stderr, process.returncode or 0


async def _kill(container: str, docker_bin: str) -> None:
    """Stop the container the timed-out client left behind. Best effort."""
    try:
        killer = await asyncio.create_subprocess_exec(
            docker_bin, "kill", container,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(killer.wait(), timeout=15)
    except (OSError, asyncio.TimeoutError):
        pass  # `--rm` cleans up whenever it does exit


async def jittered_sleep(seconds: float) -> None:
    """Sleep with jitter, so parallel work does not retry in lockstep."""
    await asyncio.sleep(seconds + random.uniform(0, seconds * 0.25))
