import asyncio
import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from ..models.job import Job, JobEvent
from ..services.jobs import JobNotFoundError, JobRegistry, get_registry

router = APIRouter(tags=["jobs"])

# Sent when nothing has happened for a while. Without it an idle connection is
# indistinguishable from a dead one, and proxies close it.
_HEARTBEAT_SECONDS = 15.0


@router.get("/jobs", response_model=list[Job])
async def list_jobs(
    paper_id: Optional[str] = Query(None),
    registry: JobRegistry = Depends(get_registry),
) -> list[Job]:
    """Jobs in this process, newest first."""
    return registry.list(paper_id)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(
    job_id: str, registry: JobRegistry = Depends(get_registry)
) -> Job:
    try:
        return registry.get(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    request: Request,
    registry: JobRegistry = Depends(get_registry),
) -> StreamingResponse:
    """Server-sent events for one job.

    SSE rather than a WebSocket: this is one-way, it is plain HTTP so it needs
    no protocol upgrade, and browsers reconnect it automatically. The reference
    project used a WebSocket and had to hand-roll keepalives and reconnection
    for a stream that never carries a client message.

    Past events are replayed first, so a subscriber that arrives late still
    sees the whole build rather than joining midway.
    """
    try:
        job = registry.get(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")

    queue = registry.subscribe(job_id)

    async def stream() -> AsyncIterator[str]:
        try:
            for event in list(job.events):
                yield _sse(event)
            if job.status.finished:
                yield _sse_status(job)
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=_HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event is None:  # the job finished and closed the stream
                    yield _sse_status(job)
                    return
                yield _sse(event)
        finally:
            registry.unsubscribe(job_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells nginx not to buffer, which would defeat the whole point.
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: JobEvent) -> str:
    payload = event.model_dump(mode="json")
    payload["fraction"] = event.fraction
    return f"event: progress\ndata: {json.dumps(payload)}\n\n"


def _sse_status(job: Job) -> str:
    payload = {
        "status": job.status.value,
        "video_url": job.video_url,
        "error": job.error,
    }
    return f"event: end\ndata: {json.dumps(payload)}\n\n"
