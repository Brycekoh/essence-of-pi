"""Narration via Kokoro, running in its own container.

Kokoro is an 82M-parameter model that sounds markedly more human than Piper.
It costs a separate 2.88 GB image, because it needs torch and the render image
does not -- layering it on would make every render pull a speech model.

Still local, still no key, still `--network none`: the weights are baked in at
build time and `HF_HUB_OFFLINE=1` makes a missing voice fail immediately rather
than hang on a download that cannot happen. Every voice that might be used has
to be warmed in the Dockerfile.

Two differences from Piper worth knowing:

- **Speed is inverted.** Piper's `length_scale` above 1.0 is slower; Kokoro's
  `speed` below 1.0 is slower. The config exposes Kokoro's own convention
  rather than pretending they are the same knob.
- **There is no sentence-silence flag.** The pause is inserted by
  `kokoro_say.py`, which splits sentences before synthesis -- measured, the
  pipeline returned a whole three-sentence line as one chunk, so padding
  between its chunks did nothing.
"""

import shutil
from pathlib import Path

from ..container import CONTAINER_WORKDIR, ContainerError, ContainerTimeout
from ..container import build_argv, container_name
from ..container import run as run_container
from .base import SpeechError


class KokoroSpeech:
    suffix = ".wav"

    def __init__(
        self,
        *,
        image: str,
        voice: str = "af_bella",
        speed: float = 0.92,
        sentence_silence: float = 0.35,
        memory: str = "4g",  # torch needs more headroom than piper
        cpus: str = "2",
        docker_bin: str = "docker",
        timeout: float = 300.0,
    ):
        self.image = image
        self.voice = voice
        self.speed = speed
        self.sentence_silence = sentence_silence
        self.memory = memory
        self.cpus = cpus
        self.docker_bin = docker_bin
        self.timeout = timeout

    def build_argv(self, *, workdir: Path, container: str) -> list[str]:
        """The exact command line, split out so the flags stay testable."""
        return build_argv(
            image=self.image,
            command=[
                "python", "/opt/kokoro_say.py",
                f"{CONTAINER_WORKDIR}/line.txt",
                f"{CONTAINER_WORKDIR}/out.wav",
                self.voice,
                str(self.speed),
                str(self.sentence_silence),
            ],
            workdir=workdir,
            container=container,
            memory=self.memory,
            cpus=self.cpus,
            docker_bin=self.docker_bin,
        )

    async def say(self, text: str, destination: Path) -> Path:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise SpeechError("Nothing to say.")

        destination.parent.mkdir(parents=True, exist_ok=True)
        work = destination.parent / f".tts-{container_name('')[1:]}"
        work.mkdir(parents=True, exist_ok=True)

        try:
            (work / "line.txt").write_text(cleaned, encoding="utf-8")
            name = container_name("eop-kokoro")
            argv = self.build_argv(workdir=work, container=name)

            try:
                _, stderr, code = await run_container(
                    argv, container=name, timeout=self.timeout, docker_bin=self.docker_bin
                )
            except ContainerTimeout as exc:
                raise SpeechError(f"Narration timed out: {exc}") from exc
            except ContainerError as exc:
                raise SpeechError(
                    f"Could not run Kokoro: {exc}. Is the image built? "
                    "docker build -f Dockerfile.kokoro -t essence-of-pi/tts:kokoro ."
                ) from exc

            produced = work / "out.wav"
            if code != 0 or not produced.exists():
                tail = stderr.strip().splitlines()[-1] if stderr.strip() else "no output"
                raise SpeechError(f"Kokoro exited {code} without producing audio: {tail}")
            if produced.stat().st_size == 0:
                raise SpeechError("Kokoro produced an empty file.")

            shutil.move(str(produced), destination)
            return destination
        finally:
            shutil.rmtree(work, ignore_errors=True)
