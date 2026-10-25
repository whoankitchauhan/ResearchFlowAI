"""FastAPI interface for the existing research pipeline."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from pipeline import run_research_pipeline

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"
MAX_STORED_JOBS = 100
JOB_RETENTION = timedelta(hours=24)
JOB_CAPACITY = 8

JobStatus = Literal["queued", "running", "completed", "failed"]


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=500)

    @field_validator("topic")
    @classmethod
    def normalize_topic(cls, topic: str) -> str:
        topic = topic.strip()
        if len(topic) < 3:
            raise ValueError("Topic must contain at least 3 non-whitespace characters.")
        return topic


class ResearchJobResponse(BaseModel):
    id: UUID
    topic: str
    status: JobStatus
    stage: str
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    result: dict[str, str] | None = None
    error: str | None = None


@dataclass
class ResearchJob:
    id: UUID
    topic: str
    status: JobStatus
    stage: str
    progress: int
    created_at: datetime
    updated_at: datetime
    result: dict[str, str] | None = None
    error: str | None = None

    def response(self) -> ResearchJobResponse:
        return ResearchJobResponse.model_validate(asdict(self))


app = FastAPI(
    title="ResearchFlowAI",
    description="A web interface for the multi-stage AI research pipeline.",
    version="1.0.0",
)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research")
_job_slots = BoundedSemaphore(JOB_CAPACITY)
_jobs_lock = Lock()
_jobs: dict[UUID, ResearchJob] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prune_jobs(now: datetime) -> None:
    expired = [
        job_id
        for job_id, job in _jobs.items()
        if job.status in ("completed", "failed")
        and now - job.updated_at > JOB_RETENTION
    ]
    for job_id in expired:
        del _jobs[job_id]

    while len(_jobs) >= MAX_STORED_JOBS:
        terminal_jobs = [
            job for job in _jobs.values()
            if job.status in ("completed", "failed")
        ]
        if not terminal_jobs:
            break
        oldest = min(terminal_jobs, key=lambda job: job.updated_at)
        del _jobs[oldest.id]


def _run_job(job_id: UUID, topic: str) -> None:
    def update_progress(stage: str, progress: int) -> None:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.status = "running"
                job.stage = stage
                job.progress = progress
                job.updated_at = _now()

    try:
        result = run_research_pipeline(topic, progress_callback=update_progress)
    except Exception:
        logger.exception("Research job %s failed.", job_id)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.status = "failed"
                job.error = (
                    "Research could not be completed. Check the server logs "
                    "and confirm the required API credentials are configured."
                )
                job.updated_at = _now()
    else:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.status = "completed"
                job.stage = "completed"
                job.progress = 100
                job.result = result
                job.updated_at = _now()
    finally:
        _job_slots.release()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/jobs",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["research"],
)
def create_job(request: ResearchRequest) -> ResearchJobResponse:
    if not _job_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Research capacity is full. Try again when a current run finishes.",
        )

    now = _now()
    job = ResearchJob(
        id=uuid4(),
        topic=request.topic,
        status="queued",
        stage="queued",
        progress=0,
        created_at=now,
        updated_at=now,
    )

    with _jobs_lock:
        _prune_jobs(now)
        if len(_jobs) >= MAX_STORED_JOBS:
            _job_slots.release()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The job history is full. Please retry later.",
            )
        _jobs[job.id] = job

    try:
        _executor.submit(_run_job, job.id, job.topic)
    except Exception as exc:
        with _jobs_lock:
            _jobs.pop(job.id, None)
        _job_slots.release()
        logger.exception("Could not queue research job %s.", job.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The research service is temporarily unavailable.",
        ) from exc

    with _jobs_lock:
        return job.response()


@app.get(
    "/api/jobs/{job_id}",
    response_model=ResearchJobResponse,
    tags=["research"],
)
def get_job(job_id: UUID) -> ResearchJobResponse:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Research job not found.",
            )
        return job.response()
