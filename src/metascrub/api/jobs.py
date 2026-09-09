from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from ..models import BatchReport
from ..report import render_html_report, render_json_report

# work(log, run_path) -> BatchReport. Takes run_path explicitly (assigned
# before the job starts) so the worker never races on an attribute the
# route handler sets only after submit() returns.
JobWork = Callable[[Callable[[str], None], str], BatchReport]


class JobQueueFull(RuntimeError):
    """Raised by JobStore.submit() when max_pending jobs are already
    queued or running — turns an unauthenticated caller flooding the
    service into a bounded 429 instead of unbounded memory growth.
    """


@dataclass
class Job:
    job_id: str
    run_id: str
    output_dir: str
    report_lang: str
    file_count: int = 0
    status: str = "queued"  # queued | running | done | error
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    log_lines: list[str] = field(default_factory=list)
    report: BatchReport | None = None

    @property
    def run_path(self) -> str:
        return os.path.join(self.output_dir, self.run_id)


class JobStore:
    """In-memory job registry backed by a bounded thread pool. Completed
    reports and cleaned files are persisted under output_dir/<run_id>/;
    only live job-tracking state is lost on a restart.
    """

    _LOG_LIMIT = 1000

    def __init__(self, *, output_dir: str, max_workers: int = 2, max_jobs_kept: int = 200,
                 max_pending: int = 50) -> None:
        self.output_dir = output_dir
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="metascrub-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._max_jobs_kept = max_jobs_kept
        self._max_pending = max_pending

    def submit(self, *, report_lang: str, file_count: int, work: JobWork) -> Job:
        with self._lock:
            pending = sum(1 for j in self._jobs.values() if j.status in ("queued", "running"))
            if pending >= self._max_pending:
                raise JobQueueFull(
                    f"{pending} job(s) already queued or running (limit {self._max_pending})."
                )
            job_id = uuid.uuid4().hex[:12]
            run_id = f"api-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{job_id[:8]}"
            job = Job(job_id=job_id, run_id=run_id, output_dir=self.output_dir,
                      report_lang=report_lang, file_count=file_count)
            self._jobs[job_id] = job
            self._evict_locked()
        self._executor.submit(self._run, job, work)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _evict_locked(self) -> None:
        if len(self._jobs) <= self._max_jobs_kept:
            return
        finished = sorted(
            (j for j in self._jobs.values() if j.status in ("done", "error")),
            key=lambda j: j.created_at,
        )
        for j in finished:
            if len(self._jobs) <= self._max_jobs_kept:
                break
            self._jobs.pop(j.job_id, None)

    def _push_log(self, job: Job, message: str) -> None:
        with self._lock:
            job.log_lines.append(message)
            if len(job.log_lines) > self._LOG_LIMIT:
                job.log_lines = job.log_lines[-self._LOG_LIMIT:]

    def _run(self, job: Job, work: JobWork) -> None:
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        try:
            report = work(lambda m: self._push_log(job, m), job.run_path)
            job.report = report
            os.makedirs(job.run_path, exist_ok=True)
            with open(os.path.join(job.run_path, "report.json"), "w", encoding="utf-8") as fh:
                fh.write(render_json_report(report))
            with open(os.path.join(job.run_path, "report.html"), "w", encoding="utf-8") as fh:
                fh.write(render_html_report(report, lang=job.report_lang))
            job.status = "done"
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            job.status = "error"
            self._push_log(job, f"! job failed: {exc}")
        finally:
            job.finished_at = datetime.now(timezone.utc)
