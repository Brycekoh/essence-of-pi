"""Narration via Piper, running inside the render image.

Why this rather than a hosted voice:

- **No quota.** Milestone 4 established that the scarce resource here is
  requests per day. Narration competing with code generation for the same
  twenty would be a bad trade for a voice.
- **No key, no network.** The voice is baked into the image at build time, so
  synthesis runs in the same `--network none` container as everything else.
- **Deterministic.** The same text gives the same audio, which makes builds
  reproducible and cacheable in a way a hosted API never is.

It costs about 260 MB on top of the base image -- Piper is ONNX, so this is
the cheap end of local TTS. Kokoro sounds better and drags in torch, which
would have taken the image past 5 GB.

The pacing knobs matter as much as the voice. gTTS runs sentences together
with no breath between ideas; `--sentence-silence` inserts a real pause, and
`--length-scale` slows delivery down to something an explainer can follow.
"""

import shutil
from pathlib import Path

from ..container import CONTAINER_WORKDIR, ContainerError, ContainerTimeout
from ..container import build_argv, container_name
from ..container import run as run_container
from .base import SpeechError


class PiperSpeech:
    suffix = ".wav"

    def __init__(
        self,
        *,
        image: str,
        voice: str = "/opt/voices/en_US-lessac-medium.onnx",
        sentence_silence: float = 0.45,
        length_scale: float = 1.0,
        memory: str = "1g",
        cpus: str = "2",
        docker_bin: str = "docker",
        timeout: float = 180.0,
    ):
        self.image = image
        self.voice = voice
        self.sentence_silence = sentence_silence
        self.length_scale = length_scale
        self.memory = memory
        self.cpus = cpus
        self.docker_bin = docker_bin
        self.timeout = timeout

    def build_argv(self, *, workdir: Path, container: str) -> list[str]:
        """The exact command line, split out so the flags stay testable.

        Narration gets the same sandbox as rendering. It has no business
        reaching the network either.
        """
        return build_argv(
            image=self.image,
            command=[
                "-m", self.voice,
                "-i", f"{CONTAINER_WORKDIR}/line.txt",
                "-f", f"{CONTAINER_WORKDIR}/out.wav",
                "--sentence-silence", str(self.sentence_silence),
                "--length-scale", str(self.length_scale),
            ],
            workdir=workdir,
            container=container,
            memory=self.memory,
            cpus=self.cpus,
            docker_bin=self.docker_bin,
            entrypoint="/opt/piper/bin/piper",
        )

    async def say(self, text: str, destination: Path) -> Path:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise SpeechError("Nothing to say.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        work = destination.parent / f".tts-{container_name('')[1:]}"
        work.mkdir(parents=True, exist_ok=True)

        try:
            # Piper reads a file rather than stdin: `container.run` does not
            # wire up stdin, and a file keeps the text out of the argv where a
            # long narration would hit command-line length limits.
            (work / "line.txt").write_text(cleaned, encoding="utf-8")

            name = container_name("eop-tts")
            argv = self.build_argv(workdir=work, container=name)

            try:
                _, stderr, code = await run_container(
                    argv, container=name, timeout=self.timeout, docker_bin=self.docker_bin
                )
            except ContainerTimeout as exc:
                raise SpeechError(f"Narration timed out: {exc}") from exc
            except ContainerError as exc:
                raise SpeechError(
                    f"Could not run Piper: {exc}. Is the render image built? "
                    "docker build -f Dockerfile.render -t essence-of-pi/render:latest ."
                ) from exc

            produced = work / "out.wav"
            if code != 0 or not produced.exists():
                raise SpeechError(
                    f"Piper exited {code} without producing audio: "
                    f"{stderr.strip().splitlines()[-1] if stderr.strip() else 'no output'}"
                )
            if produced.stat().st_size == 0:
                raise SpeechError("Piper produced an empty file.")

            shutil.move(str(produced), destination)
            return destination
        finally:
            shutil.rmtree(work, ignore_errors=True)
