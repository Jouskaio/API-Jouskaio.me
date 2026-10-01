import pytest

from jouskaio_api.core.errors import ConflictError, NotFoundError
from jouskaio_api.core.jobs import JobRegistry, JobStatus


def test_create_rejects_a_second_active_job_of_the_same_kind() -> None:
    jobs = JobRegistry()
    jobs.create("sync")
    with pytest.raises(ConflictError):
        jobs.create("sync")
    jobs.create("other-kind")  # different kinds do not block each other


def test_successful_job_stores_its_result() -> None:
    jobs = JobRegistry()
    job = jobs.create("sync")
    jobs.execute(job.id, lambda: {"ok": True})
    done = jobs.get(job.id)
    assert done.status is JobStatus.SUCCEEDED
    assert done.result == {"ok": True}
    assert done.finished_at is not None
    jobs.create("sync")  # no longer active, a new one is allowed


def test_domain_error_message_is_kept() -> None:
    jobs = JobRegistry()
    job = jobs.create("sync")

    def work() -> object:
        raise ConflictError("nope")

    jobs.execute(job.id, work)
    failed = jobs.get(job.id)
    assert failed.status is JobStatus.FAILED
    assert failed.error == "nope"


def test_unexpected_error_does_not_leak_details() -> None:
    jobs = JobRegistry()
    job = jobs.create("sync")

    def work() -> object:
        raise RuntimeError("secret path /etc/shadow")

    jobs.execute(job.id, work)
    failed = jobs.get(job.id)
    assert failed.status is JobStatus.FAILED
    assert failed.error is not None
    assert "shadow" not in failed.error


def test_unknown_job_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        JobRegistry().get("missing")


def test_history_is_trimmed_but_active_jobs_are_kept() -> None:
    jobs = JobRegistry(max_history=2)
    for kind in ("a", "b", "c"):
        job = jobs.create(kind)
        jobs.execute(job.id, lambda: None)
    assert [j.kind for j in jobs.list()] == ["c", "b"]
