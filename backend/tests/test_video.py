import json
import shutil
import subprocess
import time

import pytest

from app.models import ConceptExtraction, ManimScene, SceneSpec, SceneSplit
from app.scenes import SCENE_NAME, build_scene
from app.scenes.title_card import _literal, _wrap
from app.services.render import ManimDockerRenderer, RenderError, RenderTimeout
from app.services.store import PaperStore

from .conftest import upload
from .test_concepts import draft


GOOD_CODE = """from manim import *


class ConceptScene(Scene):
    def construct(self):
        self.play(Write(Text("hello")))
        self.wait(1.5)
"""


def scene(code: str = GOOD_CODE, plan: str = "A word appears.") -> ManimScene:
    return ManimScene(plan=plan, code=code)


def split(*narrations: str) -> SceneSplit:
    return SceneSplit(
        scenes=[SceneSpec(narration=n, visual="show it") for n in narrations]
    )


def queue_video(stub_llm, *narrations: str) -> None:
    """One split call, then one generation call per scene."""
    stub_llm.queue(split(*narrations))
    for _ in narrations:
        stub_llm.queue(scene())


def build_video(client, paper_id, concept_id, timeout: float = 10.0):
    """POST the job and poll until it finishes.

    The endpoint returns 202 immediately now, so a test that wants the finished
    article has to wait for it -- exactly like a real client does.
    """
    started = client.post(f"/api/papers/{paper_id}/concepts/{concept_id}/video")
    assert started.status_code == 202, started.text
    job_id = started.json()["id"]

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("succeeded", "failed"):
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


# --- the endpoint ---------------------------------------------------------


def test_render_produces_a_playable_url(client, rendered, stub_llm, stub_speech):
    paper_id, concept_id = rendered
    queue_video(stub_llm, "First line.", "Second line.")

    job = build_video(client, paper_id, concept_id)

    assert job["status"] == "succeeded"
    assert job["video_url"].endswith(f"/concepts/{concept_id}/video")
    assert sorted(stub_speech.said) == ["First line.", "Second line."]

    # The progress trail is the milestone: a caller can watch this happen.
    stages = [e["stage"] for e in job["events"]]
    assert stages[0] == "split" and stages[-1] == "done"
    assert "animate" in stages and "stitch" in stages

    video = client.get(job["video_url"])
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert video.content.startswith(b"\x00\x00\x00\x1cftyp")


def test_video_is_404_until_rendered(client, rendered):
    paper_id, concept_id = rendered
    response = client.get(f"/api/papers/{paper_id}/concepts/{concept_id}/video")
    assert response.status_code == 404
    assert "POST" in response.json()["detail"]


def test_render_attaches_the_url_to_the_concept(client, rendered, stub_llm):
    paper_id, concept_id = rendered
    queue_video(stub_llm, "One line.")
    assert client.get(f"/api/papers/{paper_id}/concepts/{concept_id}").json()["video_url"] is None

    build_video(client, paper_id, concept_id)

    concept = client.get(f"/api/papers/{paper_id}/concepts/{concept_id}").json()
    assert concept["video_url"].endswith(f"/concepts/{concept_id}/video")


def test_every_scene_failing_fails_the_job(client, rendered, stub_llm, stub_renderer):
    """A failed build is a failed job, not a failed request."""
    paper_id, concept_id = rendered
    queue_video(stub_llm, "One line.", "Two line.")
    for _ in range(4):  # enough corrections for both scenes
        stub_llm.queue(scene())
    stub_renderer.error = RenderError("manim exited with code 1", stderr="boom", exit_code=1)

    job = build_video(client, paper_id, concept_id)

    assert job["status"] == "failed"
    assert job["video_url"] is None
    assert "boom" not in json.dumps(job), "renderer stderr never reaches the client"


def test_unknown_ids_are_404_before_any_model_call(client, rendered, stub_llm):
    """A bad id must not cost a model call."""
    paper_id, _ = rendered
    before = len(stub_llm.calls)
    assert client.post(f"/api/papers/{paper_id}/concepts/nope/video").status_code == 404
    assert len(stub_llm.calls) == before


def test_unknown_paper_is_404(client):
    assert client.post("/api/papers/nope/concepts/nope/video").status_code == 404


def test_deleting_a_paper_removes_its_videos(client, rendered, settings, stub_llm):
    paper_id, concept_id = rendered
    queue_video(stub_llm, "One line.")
    build_video(client, paper_id, concept_id)
    video = settings.videos_dir / f"{concept_id}.mp4"
    assert video.exists()

    client.delete(f"/api/papers/{paper_id}")
    assert not video.exists()


# --- the generated scene --------------------------------------------------


def test_scene_code_compiles_and_names_its_scene():
    code, scene_name = build_scene(_concept())
    compile(code, "scene.py", "exec")  # syntax, at least, is guaranteed
    assert f"class {scene_name}(Scene)" in code


def test_concept_text_is_embedded_as_data_not_code():
    """A concept name is untrusted text on its way into a Python file.

    It must land inside a string literal, so that nothing in it can ever be
    parsed as an expression or a statement.
    """
    hostile = _concept(name='"); import os; os.system("rm -rf /"); x = ("')
    code, _ = build_scene(hostile)

    compile(code, "scene.py", "exec")
    # The dangerous text appears exactly once, and only inside a literal.
    assert _literal(hostile.name[:60]) in code
    assert "import os" not in code.replace(_literal(hostile.name[:60]), "")


def test_literal_survives_quotes_backslashes_and_newlines():
    for value in ['say "hi"', r"back\slash", "two\nlines", "emoji 🥧"]:
        assert eval(_literal(value)) == value  # noqa: S307 -- testing the escaper


def test_wrap_limits_lines_and_collapses_whitespace():
    lines = _wrap("word " * 200, width=20, max_lines=3)
    assert len(lines) == 3
    assert lines[-1].endswith("...")
    assert _wrap("a\n\n  b") == ["a b"]


# --- the real renderer ----------------------------------------------------


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "image", "inspect", "manimcommunity/manim:stable"],
            capture_output=True,
            timeout=30,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def test_docker_argv_locks_down_the_container(tmp_path):
    """The flags that make milestone 4 safe are asserted, not assumed."""
    renderer = ManimDockerRenderer(image="img", quality="-ql", memory="1g", cpus="1")
    argv = renderer.build_argv(
        workdir=tmp_path, container="eop-render-test", scene_name="ConceptCard"
    )

    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--memory" in argv and argv[argv.index("--memory") + 1] == "1g"
    assert "--cpus" in argv and argv[argv.index("--cpus") + 1] == "1"
    assert "--rm" in argv
    assert "--name" in argv, "an unnamed container cannot be killed on timeout"
    assert argv[-2:] == ["scene.py", "ConceptCard"]
    assert f"{tmp_path}:/work" in argv
    # Without --workdir the image's own WORKDIR wins and `scene.py` is not
    # found -- which is exactly how this broke once.
    assert "--workdir" in argv and argv[argv.index("--workdir") + 1] == "/work"


@pytest.mark.skipif(
    not _docker_available(),
    reason="needs Docker running with manimcommunity/manim:stable pulled",
)
@pytest.mark.slow
async def test_real_render_produces_a_real_mp4(tmp_path):
    """The only test that runs manim. Minutes, not milliseconds."""
    renderer = ManimDockerRenderer(image="manimcommunity/manim:stable", quality="-ql")
    code, scene_name = build_scene(_concept())
    destination = tmp_path / "out.mp4"

    result = await renderer.render(
        code=code, scene_name=scene_name, destination=destination, timeout=600
    )

    assert destination.exists()
    assert destination.stat().st_size > 10_000
    assert destination.read_bytes()[4:8] == b"ftyp"
    assert result.seconds > 0


# --- helpers --------------------------------------------------------------


def _concept(**overrides):
    from app.models import Concept

    base = draft(**{k: v for k, v in overrides.items() if k != "id"}).model_dump()
    base.update(id="c1", paper_id="p1")
    return Concept(**base)
