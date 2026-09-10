from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from ..models import BatchReport
from ..report import render_html_report, render_json_report

# work(log, run_path) -> BatchReport. Takes run_path explicitly (assigned
# before the job starts) so the worker never races on an attribute the
# route handler sets only after submit() returns.
JobWork = Callable[[Callable[[str], None], str], BatchReport]


class JobQueueFull(RuntimeError):
    """Raised by JobStore.submit() when max_pending jobs are already
    queued or running — a bounded 429 instead of unbounded growth.
    """


class Job:
    __slots__ = ("job_id", "run_id", "output_dir", "report_lang", "file_count", "status",
                 "created_at", "started_at", "finished_at", "error", "log_lines", "summary")

    def __init__(self, *, job_id: str, run_id: str, output_dir: str, report_lang: str,
                 file_count: int = 0, status: str = "queued",
                 created_at: datetime | None = None, started_at: datetime | None = None,
                 finished_at: datetime | None = None, error: str | None = None,
                 summary: dict | None = None) -> None:
        self.job_id = job_id
        self.run_id = run_id
        self.output_dir = output_dir
        self.report_lang = report_lang
        self.file_count = file_count
        self.status = status
        self.created_at = created_at or datetime.now(timezone.utc)
        self.started_at = started_at
        self.finished_at = finished_at
        self.error = error
        self.summary = summary          # JobSummary dict, or None until done
        self.log_lines: list[str] = []  # never persisted — process-local only

    @property
    def run_path(self) -> str:
        return os.path.join(self.output_dir, self.run_id)


class JobStore:
    """Job registry backed by a bounded thread pool and a SQLite file
    (`<output_dir>/jobs.db`) so job status survives a process restart.
    Log lines stay in memory only; a job's report.json / report.html and
    cleaned files are on disk under `<output_dir>/<run_id>/`.
    """

    _LOG_LIMIT = 1000

    def __init__(self, *, output_dir: str, max_workers: int = 2, max_jobs_kept: int = 500,
                 max_pending: int = 50, run_ttl_days: int = 0) -> None:
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="metascrub-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._max_jobs_kept = max_jobs_kept
        self._max_pending = max_pending
        self._run_ttl_days = run_ttl_days

        self._db = sqlite3.connect(os.path.join(output_dir, "jobs.db"), check_same_thread=False)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, run_id TEXT, report_lang TEXT, file_count INTEGER,
                status TEXT, created_at TEXT, started_at TEXT, finished_at TEXT,
                error TEXT, summary_json TEXT
            )""")
        self._db.commit()
        self._recover()
        if run_ttl_days > 0:
            self._sweep_expired()

    # ------------------------------------------------------------------ persistence

    def _recover(self) -> None:
        rows = self._db.execute(
            "SELECT job_id, run_id, report_lang, file_count, status, created_at, started_at, "
            "finished_at, error, summary_json FROM jobs"
        ).fetchall()
        for (job_id, run_id, lang, fc, status, created, started, finished, error, summary_json) in rows:
            if status in ("queued", "running"):
                status, error = "error", (error or "interrupted by a service restart")
                finished = finished or _now_iso()
                self._db.execute("UPDATE jobs SET status=?, error=?, finished_at=? WHERE job_id=?",
                                 (status, error, finished, job_id))
            self._jobs[job_id] = Job(
                job_id=job_id, run_id=run_id, output_dir=self.output_dir, report_lang=lang or "en",
                file_count=fc or 0, status=status, created_at=_parse(created),
                started_at=_parse(started), finished_at=_parse(finished), error=error,
                summary=json.loads(summary_json) if summary_json else None,
            )
        self._db.commit()

    def _persist(self, job: Job) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job.job_id, job.run_id, job.report_lang, job.file_count, job.status,
                 _iso(job.created_at), _iso(job.started_at), _iso(job.finished_at), job.error,
                 json.dumps(job.summary) if job.summary else None),
            )
            self._db.commit()

    def _sweep_expired(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._run_ttl_days)
        for job in list(self._jobs.values()):
            if job.status in ("done", "error") and job.created_at < cutoff:
                shutil.rmtree(job.run_path, ignore_errors=True)
                with self._lock:
                    self._jobs.pop(job.job_id, None)
                    self._db.execute("DELETE FROM jobs WHERE job_id=?", (job.job_id,))
                    self._db.commit()

    # ------------------------------------------------------------------ api

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
        self._persist(job)
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
        try:
            self._db.close()
        except sqlite3.Error:
            pass

    # ------------------------------------------------------------------ internals

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
            self._db.execute("DELETE FROM jobs WHERE job_id=?", (j.job_id,))
        self._db.commit()

    def _push_log(self, job: Job, message: str) -> None:
        with self._lock:
            job.log_lines.append(message)
            if len(job.log_lines) > self._LOG_LIMIT:
                job.log_lines = job.log_lines[-self._LOG_LIMIT:]

    def _run(self, job: Job, work: JobWork) -> None:
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        self._persist(job)
        try:
            report = work(lambda m: self._push_log(job, m), job.run_path)
            os.makedirs(job.run_path, exist_ok=True)
            with open(os.path.join(job.run_path, "report.json"), "w", encoding="utf-8") as fh:
                fh.write(render_json_report(report))
            with open(os.path.join(job.run_path, "report.html"), "w", encoding="utf-8") as fh:
                fh.write(render_html_report(report, lang=job.report_lang))
            job.summary = _summary_dict(report)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001
            job.error = str(exc)
            job.status = "error"
            self._push_log(job, f"! job failed: {exc}")
        finally:
            job.finished_at = datetime.now(timezone.utc)
            self._persist(job)


def _summary_dict(report: BatchReport) -> dict:
    return {
        "files": len(report.results),
        "by_status": report.counts,
        "fields_removed": report.fields_removed,
        "files_with_residual": len(report.files_with_residual),
        "files_errored": len(report.errored),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None
