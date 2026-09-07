"""Running video builds off the request path, with progress you can watch.

**What this is:** an in-process job registry. Jobs run as asyncio tasks, all
renders share one semaphore so the machine is not asked to run six containers
at once, and progress is published to any number of subscribers.

**What this is not:** a distributed queue. Jobs live in this process's memory,
so a restart loses them and a second uvicorn worker would not see them. That is
a deliberate stopping point, not an oversight -- Redis plus a separate worker is
real infrastructure, and milestone 8 rewrites persistence anyway. Everything
here sits behind `JobRegistry`, so the swap is one class.

The honest limitation, stated once: **run this with a single worker.**
"""

import asyncio
import uuid
from typing import Awaitable, Callable, Optional

from ..models.job import Job, JobEvent, JobStatus

# A progress callback. Handed to the pipeline so it can report without knowing
# anything about jobs, HTTP, or who is listening.
Progress = Callable[[JobEvent], None]


class JobNotFoundError(KeyError):
    """No job with that id."""


class JobRegistry:
    """Jobs, their events, and the subscribers watching them."""

    def __init__(self, max_parallel: int = 2, history: int = 50):
        # Bounds *renders*, not jobs. Each container gets 2 CPUs and 2 GB, so
        # letting six run at once turns a four-minute build into a swap storm.
        self.semaphore = asyncio.Semaphore(max_parallel)
        self.max_parallel = max_parallel
        self.history = history
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # --- lifecycle --------------------------------------------------------

    def create(self, paper_id: str, concept_id: str) -> Job:
        job = Job(id=uuid.uuid4().hex, paper_id=paper_id, concept_id=concept_id)
        self._jobs[job.id] = job
        self._order.append(job.id)
        self._evict()
        return job

    def get(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(job_id) from exc

    def list(self, paper_id: Optional[str] = None) -> list[Job]:
        jobs = [self._jobs[i] for i in reversed(self._order) if i in self._jobs]
        return [j for j in jobs if paper_id is None or j.paper_id == paper_id]

    def find_active(self, concept_id: str) -> Optional[Job]:
        """An unfinished job for this concept, if one exists.

        Submitting the same concept twice while the first build is running
        would spend a second helping of quota to produce the same file.
        """
        for job in self._jobs.values():
            if job.concept_id == concept_id and not job.status.finished:
                return job
        return None

    def submit(self, job: Job, work: Callable[[Progress], Awaitable[None]]) -> Job:
        """Start `work` in the background and return immediately."""

        async def runner() -> None:
            self._set_status(job, JobStatus.RUNNING)
            try:
                await work(lambda event: self.publish(job.id, event))
                if job.status is JobStatus.RUNNING:
                    self._set_status(job, JobStatus.SUCCEEDED)
            except asyncio.CancelledError:
                self.fail(job.id, "Cancelled.")
                raise
            except Exception as exc:  # noqa: BLE001 - a job must never kill the server
                self.fail(job.id, f"{type(exc).__name__}: {exc}")
            finally:
                self._close(job.id)

        self._tasks[job.id] = asyncio.create_task(runner(), name=f"job-{job.id}")
        return job

    def succeed(self, job_id: str, video_url: str) -> Job:
        job = self.get(job_id)
        job.video_url = video_url
        self.publish(job_id, JobEvent(stage="done", message="Video ready."))
        return self._set_status(job, JobStatus.SUCCEEDED)

    def fail(self, job_id: str, error: str) -> Job:
        job = self.get(job_id)
        job.error = error
        self.publish(job_id, JobEvent(stage="failed", message=error))
        return self._set_status(job, JobStatus.FAILED)

    # --- progress ---------------------------------------------------------

    def publish(self, job_id: str, event: JobEvent) -> None:
        """Record an event and hand it to every live subscriber.

        Never blocks and never raises: a slow or dead reader must not be able
        to stall the pipeline that is reporting to it.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.events.append(event)
        job.updated_at = event.at
        for queue in list(self._subscribers.get(job_id, [])):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self, job_id: str) -> asyncio.Queue:
        """A queue of future events. Replay of past ones is the caller's job."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(job_id, []).append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        watchers = self._subscribers.get(job_id)
        if watchers and queue in watchers:
            watchers.remove(queue)
        if watchers == []:
            self._subscribers.pop(job_id, None)

    # --- internals --------------------------------------------------------

    def _set_status(self, job: Job, status: JobStatus) -> Job:
        job.status = status
        job.updated_at = JobEvent(stage="", message="").at
        return job

    def _close(self, job_id: str) -> None:
        """Wake every subscriber so a finished job's stream can end."""
        for queue in list(self._subscribers.get(job_id, [])):
            try:
                queue.put_nowait(None)  # sentinel: no more events
            except asyncio.QueueFull:
                pass
        self._tasks.pop(job_id, None)

    def _evict(self) -> None:
        """Keep the newest `history` jobs. Unbounded memory is a bug, not a feature."""
        while len(self._order) > self.history:
            oldest = self._order.pop(0)
            job = self._jobs.get(oldest)
            if job and not job.status.finished:
                self._order.append(oldest)  # never evict a running job
                return
            self._jobs.pop(oldest, None)
            self._subscribers.pop(oldest, None)


_registry: Optional[JobRegistry] = None


def get_registry() -> JobRegistry:
    """FastAPI dependency. One registry per process; tests override it."""
    global _registry
    if _registry is None:
        from ..config import get_settings

        _registry = JobRegistry(max_parallel=get_settings().max_parallel_renders)
    return _registry
