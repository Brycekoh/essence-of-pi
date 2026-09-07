from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def finished(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED)


class JobEvent(BaseModel):
    """One thing that happened, as it happened.

    Deliberately coarse. These are for a person watching a progress bar, not
    for debugging -- `detail` never carries renderer stderr, for the same
    reason scene reports do not.
    """

    at: datetime = Field(default_factory=_now)
    stage: str      # "split" | "narrate" | "animate" | "render" | "stitch" | "done"
    message: str
    scene: Optional[int] = None
    total_scenes: Optional[int] = None

    @property
    def fraction(self) -> Optional[float]:
        if self.scene and self.total_scenes:
            return min(self.scene / self.total_scenes, 1.0)
        return None


class Job(BaseModel):
    """A video build, tracked from submission to finish.

    A job exists so the HTTP request does not have to wait for it. Before
    milestone 6 a POST blocked for a split call plus up to nine model calls and
    container starts -- minutes, on a connection any proxy would time out.
    """

    id: str
    paper_id: str
    concept_id: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    events: list[JobEvent] = Field(default_factory=list)
    video_url: Optional[str] = None
    error: Optional[str] = None

    @property
    def stage(self) -> str:
        return self.events[-1].stage if self.events else "queued"
