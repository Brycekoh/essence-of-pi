"""Running a command in a container, with a timeout that actually works.

Everything this app shells out to -- manim, ffmpeg, Piper, Kokoro -- needs the
same behaviours, so they live here once:

- no network, capped memory, capped CPU
- a *named* container, because killing the `docker run` client does not stop
  the container it started; the daemon owns it
- a clear error when the daemon simply is not running

And, since milestone 8, **a way to hand files to a container when the backend
is itself in one.** A bind mount names a path on the machine running the Docker
daemon. When the backend runs on the host, that path is its own. Under docker
compose, the path the backend knows is inside *its* container, and the daemon
cannot see it -- every render would fail. So in that mode storage lives in a
named volume mounted into the backend at STORAGE_ROOT, and each sandbox mounts
only the sub-directory it needs, via `volume-subpath`.
"""

import asyncio
import os
import random
import uuid
from pathlib import Path, PurePosixPath
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


def make_scratch(path: Path) -> Path:
    """Create a scratch directory that any sandbox can write into.

    The sandboxes do not all run as the same user. The render image -- which
    also runs ffmpeg and Piper -- is uid 1000; Kokoro is root; the backend that
    creates these directories is root. On a host bind mount Docker Desktop
    papers over the difference. In a named volume the permissions are real, and
    a root-owned 755 directory is read-only to uid 1000: manim's first render
    under docker compose died with `Permission denied: '/work/media'`.

    The fix is to widen the scratch directory, never to raise the sandbox's
    privileges. Running model-written code as root to dodge a chmod would be
    exactly backwards. The directory holds one job's scratch files and lives
    inside a private volume.
    """
    path.mkdir(parents=True, exist_ok=True)
    # After mkdir, not as its mode argument: mkdir's mode is filtered by umask.
    os.chmod(path, 0o777)
    return path


def mount_args(
    workdir: Path,
    *,
    storage_volume: Optional[str],
    storage_root: Optional[str],
) -> list[str]:
    """How `workdir` reaches the container as /work.

    Host mode (no storage volume): bind-mount the absolute host path.

    Compose mode: mount the named volume, restricted to `workdir`'s path
    relative to where that volume is mounted in *this* process. A sandbox running
    model-written code sees its own scratch directory and nothing else -- not
    the uploads, not other renders.
    """
    if not storage_volume:
        # Absolute, always. Docker reads a *relative* -v source as the name of a
        # named volume rather than a path to bind, and then rejects it for having
        # invalid characters. Tests never caught this because pytest's tmp_path
        # is already absolute; a relative --out on the command line is not.
        return ["--volume", f"{Path(workdir).resolve()}:{CONTAINER_WORKDIR}"]

    root = PurePosixPath(storage_root or "/data")
    here = PurePosixPath(Path(workdir).as_posix())
    try:
        sub = here.relative_to(root)
    except ValueError as exc:
        raise ContainerError(
            f"{here} is outside the storage volume mounted at {root}, so a sandbox "
            "could not see it. Keep UPLOAD_DIR and VIDEOS_DIR inside STORAGE_ROOT."
        ) from exc
    if str(sub) in ("", "."):
        raise ContainerError(
            "Refusing to mount the whole storage volume into a sandbox; "
            "give it a sub-directory."
        )
    return [
        "--mount",
        f"type=volume,src={storage_volume},dst={CONTAINER_WORKDIR},volume-subpath={sub.as_posix()}",
    ]


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
    storage_volume: Optional[str] = None,
    storage_root: Optional[str] = None,
) -> list[str]:
    """The exact command line, split out so the sandbox flags stay testable.

    Every flag between `--name` and the image is load-bearing: from milestone 4
    the code inside `workdir` is written by a language model.

    The storage mode defaults to the STORAGE_VOLUME and STORAGE_ROOT environment
    variables. They describe how this process is *deployed* rather than what it
    does, which is why they are read here instead of being threaded through four
    services and their factories. Tests pass them explicitly; an empty string
    forces host mode.
    """
    volume = storage_volume if storage_volume is not None else os.environ.get("STORAGE_VOLUME")
    root = storage_root if storage_root is not None else os.environ.get("STORAGE_ROOT")

    argv = [
        docker_bin, "run", "--rm",
        "--name", container,
        "--network", "none",
        "--memory", memory,
        "--cpus", cpus,
        *mount_args(workdir, storage_volume=volume or None, storage_root=root or None),
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
    cannot be reached or refuses to start the container. A non-zero exit from
    the program inside is returned, not raised -- callers know better than this
    module what a failure means.
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
    if process.returncode != 0:
        if "Cannot connect to the Docker daemon" in stderr:
            raise ContainerError(
                "The Docker daemon is not running. Start Docker Desktop and retry.",
                stderr=stderr,
                exit_code=process.returncode,
            )
        # The daemon refused to *start* the container -- a bad mount, a missing
        # image, an unusable flag. The program inside never ran, so this is our
        # problem and not the program's. Docker prefixes these itself.
        if stderr.lstrip().startswith("docker:") or "Error response from daemon" in stderr:
            raise ContainerError(
                f"Docker refused to start the container: {stderr.strip().splitlines()[0]}",
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
