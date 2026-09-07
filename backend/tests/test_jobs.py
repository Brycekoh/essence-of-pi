"""The job registry and the progress stream."""

import asyncio

import pytest

from app.models.job import JobEvent, JobStatus
from app.services.jobs import JobNotFoundError, JobRegistry

from .conftest import upload
from .test_video import build_video, queue_video


# --- the registry ---------------------------------------------------------


async def test_a_job_runs_in_the_background_and_succeeds():
    registry = JobRegistry()
    job = registry.create("p1", "c1")
    done = asyncio.Event()

    async def work(progress):
        progress(JobEvent(stage="animate", message="working"))
        registry.succeed(job.id, "/video")
        done.set()

    registry.submit(job, work)
    await asyncio.wait_for(done.wait(), timeout=2)
    await asyncio.sleep(0)  # let the runner finish

    assert registry.get(job.id).status is JobStatus.SUCCEEDED
    assert registry.get(job.id).video_url == "/video"


async def test_a_crashing_job_fails_instead_of_killing_the_server():
    """One bad job must not take the process with it."""
    registry = JobRegistry()
    job = registry.create("p1", "c1")

    async def work(progress):
        raise ValueError("something went wrong inside")

    registry.submit(job, work)
    for _ in range(50):
        if registry.get(job.id).status.finished:
            break
        await asyncio.sleep(0.01)

    finished = registry.get(job.id)
    assert finished.status is JobStatus.FAILED
    assert "something went wrong inside" in finished.error


async def test_parallelism_is_bounded_by_the_semaphore():
    """Two containers at a time, not six."""
    registry = JobRegistry(max_parallel=2)
    running = 0
    peak = 0

    async def scene():
        nonlocal running, peak
        async with registry.semaphore:
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.02)
            running -= 1

    await asyncio.gather(*(scene() for _ in range(6)))
    assert peak == 2, f"ran {peak} at once with max_parallel=2"


async def test_find_active_spots_a_build_already_running():
    registry = JobRegistry()
    job = registry.create("p1", "c1")
    assert registry.find_active("c1") is job

    registry.succeed(job.id, "/video")
    assert registry.find_active("c1") is None, "a finished job is not active"


def test_history_is_capped_but_never_evicts_a_running_job():
    registry = JobRegistry(history=3)
    running = registry.create("p1", "running")

    for i in range(5):
        finished = registry.create("p1", f"done{i}")
        registry.succeed(finished.id, "/v")

    assert registry.get(running.id).status is JobStatus.QUEUED, "still tracked"
    assert len(registry.list()) <= 4


def test_unknown_job_raises():
    with pytest.raises(JobNotFoundError):
        JobRegistry().get("nope")


def test_publish_never_blocks_on_a_full_subscriber():
    """A dead reader must not be able to stall the pipeline reporting to it."""
    registry = JobRegistry()
    job = registry.create("p1", "c1")
    queue = registry.subscribe(job.id)

    for i in range(500):  # far past the queue's maxsize
        registry.publish(job.id, JobEvent(stage="animate", message=f"event {i}"))

    assert len(registry.get(job.id).events) == 500, "every event is still recorded"
    assert queue.full()


# --- the API --------------------------------------------------------------


def test_post_returns_202_and_a_queued_job(client, rendered, stub_llm):
    paper_id, concept_id = rendered
    queue_video(stub_llm, "One line.")

    response = client.post(f"/api/papers/{paper_id}/concepts/{concept_id}/video")

    assert response.status_code == 202, "the caller must not wait minutes"
    body = response.json()
    assert body["status"] in ("queued", "running")
    assert body["video_url"] is None


def test_a_second_submission_joins_the_running_job(client, rendered, stub_llm, registry):
    """Submitting twice would spend a second helping of quota for one file."""
    paper_id, concept_id = rendered
    queue_video(stub_llm, "One line.")

    first = registry.create(paper_id, concept_id)  # pretend one is already running

    response = client.post(f"/api/papers/{paper_id}/concepts/{concept_id}/video")

    assert response.status_code == 200, "joined, not created"
    assert response.json()["id"] == first.id


def test_jobs_are_listed_newest_first(client, rendered, stub_llm):
    paper_id, concept_id = rendered
    queue_video(stub_llm, "One line.")
    build_video(client, paper_id, concept_id)

    jobs = client.get("/api/jobs", params={"paper_id": paper_id}).json()
    assert len(jobs) == 1
    assert jobs[0]["concept_id"] == concept_id


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/events").status_code == 404


def test_event_stream_replays_a_finished_job(client, rendered, stub_llm):
    """A subscriber arriving late still sees the whole build."""
    paper_id, concept_id = rendered
    queue_video(stub_llm, "One line.")
    job = build_video(client, paper_id, concept_id)

    with client.stream("GET", f"/api/jobs/{job['id']}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "event: progress" in body
    assert "event: end" in body
    assert '"status": "succeeded"' in body
    assert "Breaking" in body, "the split event is replayed, not skipped"
