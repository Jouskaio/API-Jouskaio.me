"""A tiny in-memory registry for long-running actions.

Endpoints that take time answer ``202 Accepted`` with a job id; the client polls the
job. The registry is deliberately in-memory: history is lost on restart, which is fine
for a personal tool. Swap it for a persistent implementation if that ever matters.
"""

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from jouskaio_api.core.errors import ConflictError, DomainError, NotFoundError

logger = logging.getLogger(__name__)


class JobStatus(StrEnum):
    """Lifecycle of a background job.

    - `queued`: accepted, not started yet.
    - `running`: in progress.
    - `succeeded`: finished; the result is attached.
    - `failed`: finished with an error; `error` explains why.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


_ACTIVE = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Job:
    id: str
    kind: str
    status: JobStatus
    created_at: datetime
    finished_at: datetime | None = None
    result: object | None = None
    error: str | None = None


class JobRegistry:
    """Thread-safe. At most one active job per ``kind``."""

    def __init__(self, max_history: int = 100) -> None:
        self._max_history = max_history
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()

    def create(self, kind: str) -> Job:
        with self._lock:
            if any(j.kind == kind and j.status in _ACTIVE for j in self._jobs.values()):
                raise ConflictError(f"A '{kind}' job is already in progress")
            job = Job(id=uuid.uuid4().hex, kind=kind, status=JobStatus.QUEUED, created_at=_now())
            self._jobs[job.id] = job
            self._trim()
            return replace(job)

    def execute(self, job_id: str, work: Callable[[], object]) -> None:
        """Run ``work`` and record its outcome. Never raises."""
        self._update(job_id, status=JobStatus.RUNNING)
        try:
            result = work()
        except DomainError as exc:
            logger.warning("job %s failed: %s", job_id, exc)
            self._update(job_id, status=JobStatus.FAILED, finished_at=_now(), error=str(exc))
        except Exception:
            logger.exception("job %s crashed", job_id)
            self._update(
                job_id,
                status=JobStatus.FAILED,
                finished_at=_now(),
                error="Unexpected error, see server logs",
            )
        else:
            self._update(job_id, status=JobStatus.SUCCEEDED, finished_at=_now(), result=result)

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise NotFoundError(f"Job {job_id}")
            return replace(job)

    def list(self, kind: str | None = None) -> list[Job]:
        """Newest first."""
        with self._lock:
            jobs = [replace(j) for j in self._jobs.values() if kind is None or j.kind == kind]
        return list(reversed(jobs))

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for name, value in changes.items():
                setattr(job, name, value)

    def _trim(self) -> None:
        excess = len(self._jobs) - self._max_history
        if excess <= 0:
            return
        finished = [j.id for j in self._jobs.values() if j.status not in _ACTIVE]
        for job_id in finished[:excess]:
            del self._jobs[job_id]
