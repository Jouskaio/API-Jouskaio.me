"""API and persistence models of the notes_sync module."""

from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from jouskaio_api.core.jobs import JobStatus


class NoteOutcome(StrEnum):
    """What a run did with one exported note.

    - `created`: a new Markdown note was written to the vault.
    - `updated`: the note already existed; its managed block was regenerated (your own
      edits outside the block are kept).
    - `skipped`: nothing changed since the last run (same content, same processing).
    - `unsupported`: no converter for this format (e.g. `.note`): pick PDF or RTF in Notability.
    - `conflict`: a file not managed by this module already exists at the target path, or
      its managed-block markers were removed; it is left untouched.
    - `failed`: the note could not be processed; `detail` explains why, the others go on.
    """

    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
    CONFLICT = "conflict"
    FAILED = "failed"


class NoteResult(BaseModel, frozen=True):
    """Result of one note within a run."""

    key: str = Field(
        description="Path of the exported file, relative to the inbox.",
        examples=["Courses/Algebra.pdf"],
    )
    outcome: NoteOutcome
    detail: str | None = Field(
        default=None,
        description="Vault path of the note when written, otherwise the reason.",
        examples=["Notability/Courses/Algebra.md"],
    )


class SyncReport(BaseModel):
    """What a finished run did."""

    started_at: datetime
    finished_at: datetime
    summary: dict[str, int] = Field(
        description="Number of notes per outcome (outcomes with zero notes are omitted).",
        examples=[{"created": 2, "skipped": 14, "unsupported": 1}],
    )
    results: list[NoteResult] = Field(description="One entry per file found in the inbox.")

    @classmethod
    def build(cls, started_at: datetime, finished_at: datetime, results: list[NoteResult]) -> Self:
        counts = Counter(result.outcome.value for result in results)
        return cls(
            started_at=started_at,
            finished_at=finished_at,
            summary=dict(counts),
            results=results,
        )


class SyncRecord(BaseModel, frozen=True):
    """A note already synchronised, as remembered between runs."""

    key: str = Field(
        description="Path of the exported file, relative to the inbox.",
        examples=["Courses/Algebra.pdf"],
    )
    digest: str = Field(description="SHA-256 of the exported file at the last sync.")
    vault_path: str = Field(
        description="Path of the Markdown note, relative to the vault.",
        examples=["Notability/Courses/Algebra.md"],
    )
    synced_at: datetime
    pipeline: str = Field(
        default="",
        description=(
            "Processing applied at the last sync. When it differs from the current one "
            "(OCR enabled, model changed, OCR failed), the note is processed again."
        ),
        examples=["pdf;ocr=kraken:McCATMuS_nfd_nofix_V1.mlmodel"],
    )


class RunResource(BaseModel):
    """A synchronisation run, executed in the background."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3f2a9c0d8e7b4a1c9d6e5f4a3b2c1d0e",
                    "status": "succeeded",
                    "created_at": "2026-10-01T08:00:00Z",
                    "finished_at": "2026-10-01T08:00:42Z",
                    "report": {
                        "started_at": "2026-10-01T08:00:00Z",
                        "finished_at": "2026-10-01T08:00:42Z",
                        "summary": {"created": 1, "skipped": 3},
                        "results": [
                            {
                                "key": "Courses/Algebra.pdf",
                                "outcome": "created",
                                "detail": "Notability/Courses/Algebra.md",
                            }
                        ],
                    },
                    "error": None,
                }
            ]
        }
    )

    id: str = Field(description="Run identifier, used to poll `GET /runs/{job_id}`.")
    status: JobStatus
    created_at: datetime
    finished_at: datetime | None = Field(default=None, description="Set once the run is over.")
    report: SyncReport | None = Field(default=None, description="Set when the run succeeded.")
    error: str | None = Field(
        default=None,
        description="Set when the run failed as a whole (e.g. the inbox is unreachable).",
    )
