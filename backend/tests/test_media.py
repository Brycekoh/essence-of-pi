"""The narration and media plumbing.

The stub tests run everywhere. The integration tests run ffmpeg for real and
skip themselves without Docker and the built render image.
"""

import shutil
import subprocess

import pytest

from app.services.container import CONTAINER_WORKDIR, build_argv, container_name
from app.services.media import FfmpegMedia, MediaError, StubMedia
from app.services.speech import SpeechError, StubSpeech

IMAGE = "essence-of-pi/render:latest"


# --- the seams ------------------------------------------------------------


async def test_stub_speech_records_what_it_was_asked_to_say(tmp_path):
    speech = StubSpeech()
    out = await speech.say("  Batch   normalization\n stabilises training. ", tmp_path / "a.mp3")

    assert out.exists()
    assert speech.said == ["Batch normalization stabilises training."], "whitespace collapsed"


async def test_speech_refuses_empty_text(tmp_path):
    with pytest.raises(SpeechError, match="Nothing to say"):
        await StubSpeech().say("   \n  ", tmp_path / "a.mp3")


async def test_stub_media_concat_refuses_nothing(tmp_path):
    with pytest.raises(MediaError, match="Nothing to concatenate"):
        await StubMedia().concat([], tmp_path / "out.mp4")


async def test_stub_media_records_the_call(tmp_path):
    media = StubMedia(durations={"narration.mp3": 9.0})
    assert await media.duration(tmp_path / "narration.mp3") == 9.0

    await media.mux(tmp_path / "v.mp4", tmp_path / "narration.mp3", tmp_path / "o.mp4")
    assert media.calls[-1][0] == "mux"


def test_container_argv_locks_down_ffmpeg_too(tmp_path):
    """The media container gets the same sandbox as the render container."""
    argv = build_argv(
        image=IMAGE,
        command=["-version"],
        workdir=tmp_path,
        container=container_name(),
        entrypoint="ffprobe",
    )

    assert argv[argv.index("--network") + 1] == "none"
    assert argv[argv.index("--workdir") + 1] == CONTAINER_WORKDIR
    assert argv[argv.index("--entrypoint") + 1] == "ffprobe"
    assert "--rm" in argv and "--name" in argv


# --- the real thing -------------------------------------------------------


def _image_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, timeout=30
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


requires_image = pytest.mark.skipif(
    not _image_available(),
    reason=f"needs {IMAGE}: docker build -f Dockerfile.render -t {IMAGE} .",
)


def _make(kind: str, path, seconds: float) -> None:
    """Synthesise a test clip with ffmpeg, so no fixtures are checked in."""
    source = (
        f"testsrc=duration={seconds}:size=320x240:rate=15"
        if kind == "video"
        else f"anullsrc=r=44100:cl=mono:d={seconds}"
    )
    subprocess.run(
        [
            "docker", "run", "--rm", "--entrypoint", "ffmpeg",
            "-v", f"{path.parent}:/w", IMAGE,
            "-v", "error", "-y", "-f", "lavfi", "-i", source,
            *(["-pix_fmt", "yuv420p"] if kind == "video" else []),
            f"/w/{path.name}",
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )


@requires_image
@pytest.mark.slow
async def test_probe_mux_and_concat_for_real(tmp_path):
    media = FfmpegMedia(image=IMAGE)
    video, audio = tmp_path / "v.mp4", tmp_path / "a.mp3"
    _make("video", video, 3.0)
    _make("audio", audio, 5.0)

    assert await media.duration(video) == pytest.approx(3.0, abs=0.3)
    assert await media.duration(audio) == pytest.approx(5.0, abs=0.3)

    # Narration outlasts the animation, so the last frame is held rather than
    # the sentence being cut off.
    muxed = await media.mux(video, audio, tmp_path / "muxed.mp4")
    assert await media.duration(muxed) == pytest.approx(5.0, abs=0.4), "video padded, audio intact"

    joined = await media.concat([muxed, muxed], tmp_path / "joined.mp4")
    assert await media.duration(joined) == pytest.approx(10.0, abs=0.8)


@requires_image
@pytest.mark.slow
async def test_concat_of_one_clip_is_a_copy(tmp_path):
    media = FfmpegMedia(image=IMAGE)
    clip = tmp_path / "v.mp4"
    _make("video", clip, 2.0)

    out = await media.concat([clip], tmp_path / "out.mp4")
    assert out.read_bytes() == clip.read_bytes(), "no re-encode for a single clip"
