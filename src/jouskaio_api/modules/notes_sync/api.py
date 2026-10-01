"""HTTP layer of the module: thin, no business logic."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Path

from jouskaio_api.core.errors import NotFoundError
from jouskaio_api.core.http import error_responses
from jouskaio_api.core.jobs import Job, JobRegistry
from jouskaio_api.modules.notes_sync.schemas import RunResource, SyncRecord, SyncReport
from jouskaio_api.modules.notes_sync.service import NotesSyncService

logger = logging.getLogger(__name__)

JOB_KIND = "notes_sync.run"

JobId = Annotated[str, Path(description="Run identifier returned by `POST /runs`.")]


def _to_resource(job: Job) -> RunResource:
    return RunResource(
        id=job.id,
        status=job.status,
        created_at=job.created_at,
        finished_at=job.finished_at,
        report=job.result if isinstance(job.result, SyncReport) else None,
        error=job.error,
    )


def build_router(service: NotesSyncService, jobs: JobRegistry) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/runs",
        status_code=202,
        response_model=RunResource,
        summary="Start a synchronisation run",
        response_description="The run is accepted and starts in the background.",
        responses=error_responses(409, e409="A run is already queued or in progress."),
    )
    def start_run(background: BackgroundTasks) -> RunResource:
        """Scan the inbox and synchronise every exported note into the Obsidian vault.

        The run goes on in the background: poll `GET /runs/{job_id}` until its status is
        `succeeded` (the report lists the outcome of each note) or `failed`. Only one run
        at a time; unchanged notes are skipped, so running often is cheap.
        """
        job = jobs.create(JOB_KIND)
        logger.info("notes_sync run requested job_id=%s", job.id)  # audit trail
        background.add_task(jobs.execute, job.id, service.run)
        return _to_resource(job)

    @router.get(
        "/runs",
        response_model=list[RunResource],
        summary="List recent runs",
        response_description="Runs, newest first.",
    )
    def list_runs() -> list[RunResource]:
        """Recent runs, newest first. The history is kept in memory (100 runs at most) and
        is lost when the API restarts."""
        return [_to_resource(job) for job in jobs.list(JOB_KIND)]

    @router.get(
        "/runs/{job_id}",
        response_model=RunResource,
        summary="Get a run",
        response_description="The run, with its report once it succeeded.",
        responses=error_responses(404, e404="No run with this id (or forgotten after a restart)."),
    )
    def get_run(job_id: JobId) -> RunResource:
        """Status of a run and, once finished, its per-note report or its error."""
        job = jobs.get(job_id)
        if job.kind != JOB_KIND:
            raise NotFoundError(f"Run {job_id}")
        return _to_resource(job)

    @router.get(
        "/notes",
        response_model=list[SyncRecord],
        summary="List synchronised notes",
        response_description="Every note already synchronised, sorted by inbox path.",
    )
    def list_notes() -> list[SyncRecord]:
        """Notes already synchronised into the vault, as remembered between runs."""
        return service.list_synced()

    return router
