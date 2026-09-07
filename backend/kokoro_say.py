"""Synthesise one line with Kokoro. Runs inside the TTS image, never on the host.

    kokoro_say.py <text file> <out.wav> [voice] [speed] [sentence_silence]

Kokoro has no equivalent of Piper's `--sentence-silence`, so the pause between
sentences is inserted here.

Sentences are split *before* synthesis rather than relying on the pipeline's
own chunking: measured, a three-sentence line came back as a single chunk, so
padding between chunks did nothing at all. Splitting first makes the pause a
guarantee instead of a hope.
"""

import re

import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro import KPipeline  # noqa: E402

SAMPLE_RATE = 24_000


def main() -> int:
    text = open(sys.argv[1], encoding="utf-8").read().strip()
    out = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "af_bella"
    speed = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    silence = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0

    if not text:
        print("no text", file=sys.stderr)
        return 2

    pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    sentences = split_sentences(text) if silence > 0 else [text]

    pad = np.zeros(int(SAMPLE_RATE * silence), dtype=np.float32)
    pieces: list[np.ndarray] = []
    for sentence in sentences:
        audio = [a for _, _, a in pipeline(sentence, voice=voice, speed=speed)]
        if not audio:
            continue
        if pieces:
            pieces.append(pad)
        pieces.append(np.concatenate([np.asarray(a, dtype=np.float32) for a in audio]))

    if not pieces:
        print("kokoro produced no audio", file=sys.stderr)
        return 3

    sf.write(out, np.concatenate(pieces), SAMPLE_RATE)
    return 0


def split_sentences(text: str) -> list[str]:
    """Split on sentence-ending punctuation, keeping the punctuation."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text)]
    return [p for p in parts if p] or [text]


if __name__ == "__main__":
    raise SystemExit(main())
