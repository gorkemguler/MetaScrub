from __future__ import annotations

import io
import os
import secrets
import shutil
import tempfile
import zipfile
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from werkzeug.utils import secure_filename

from .. import __version__
from ..cleaner import clean_file_list
from ..config import CleanConfig
from ..models import BatchReport
from .jobs import Job, JobQueueFull, JobStore
from .schemas import (
    HealthResponse,
    JobCreated,
    JobLogResponse,
    JobStatusResponse,
    JobSummary,
)

_CHUNK = 1024 * 1024


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _summary(report: BatchReport) -> JobSummary:
    return JobSummary(
        files=len(report.results),
        by_status=report.counts,
        fields_removed=report.fields_removed,
        files_with_residual=len(report.files_with_residual),
        files_errored=len(report.errored),
    )


def _links(request: Request, job_id: str) -> dict[str, str]:
    return {
        "self": str(request.url_for("get_job", job_id=job_id)),
        "log": str(request.url_for("get_job_log", job_id=job_id)),
        "report_json": str(request.url_for("get_job_report_json", job_id=job_id)),
        "report_html": str(request.url_for("get_job_report_html", job_id=job_id)),
        "download": str(request.url_for("get_job_download", job_id=job_id)),
    }


def _status(job: Job, request: Request) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.job_id, status=job.status, run_id=job.run_id, file_count=job.file_count,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        error=job.error,
        summary=_summary(job.report) if job.report is not None else None,
        links=_links(request, job.job_id),
    )


def _require(store: JobStore, job_id: str) -> Job:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, f"No job {job_id!r}. Jobs are in-memory and don't survive a restart.")
    return job


def _require_done(store: JobStore, job_id: str) -> Job:
    job = _require(store, job_id)
    if job.status != "done":
        raise HTTPException(409, {"job_id": job.job_id, "status": job.status, "error": job.error,
                                  "message": "Not ready — poll GET /v1/clean/{job_id} until status is 'done'."})
    return job


def create_app(*, output_dir: str = "./metascrub_cleaned", max_workers: int = 2,
               max_pending: int = 50, api_key: str | None = None,
               max_upload_mb: int = 200, max_files: int = 50) -> FastAPI:
    """MetaScrub REST API — POST files, poll the job, pull the cleaned
    files + report as a zip. Every job runs in a bounded background thread
    pool so POST returns immediately; max_pending caps queued+running jobs.

    `api_key`, when set, is required on every `/v1/*` route except
    `/v1/health` — as `X-API-Key: <key>` or `Authorization: Bearer <key>`.
    `max_upload_mb` / `max_files` bound a single request.
    """
    os.makedirs(output_dir, exist_ok=True)
    store = JobStore(output_dir=output_dir, max_workers=max_workers, max_pending=max_pending)
    max_upload_bytes = max_upload_mb * 1024 * 1024

    def require_key(request: Request) -> None:
        if not api_key:
            return
        supplied = request.headers.get("x-api-key")
        if not supplied:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                supplied = auth[7:]
        if not (supplied and secrets.compare_digest(supplied, api_key)):
            raise HTTPException(401, "missing or invalid API key")

    guard = [Depends(require_key)]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        store.shutdown()

    app = FastAPI(
        title="MetaScrub API",
        version=__version__,
        description="Job-based bulk metadata scrubbing for PDF/Office/image files. "
                    "No built-in authentication — see the README before exposing this.",
        lifespan=lifespan,
    )

    @app.get("/v1/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        active = sum(1 for j in store.list() if j.status in ("queued", "running"))
        return HealthResponse(status="ok", version=__version__, active_jobs=active)

    @app.post("/v1/clean", response_model=JobCreated, status_code=202, tags=["clean"],
              dependencies=guard)
    async def create_clean(
        request: Request,
        files: list[UploadFile] = File(..., description="Files to scrub."),
        keep_title: bool = Form(False),
        keep_color_profile: bool = Form(True),
        in_place: bool = Form(False, description="Ignored — the API always returns cleaned copies."),
        report_lang: str = Form("en"),
    ) -> JobCreated:
        uploads = [f for f in files if f.filename]
        if not uploads:
            raise HTTPException(422, "No files provided.")
        if len(uploads) > max_files:
            raise HTTPException(413, f"too many files ({len(uploads)} > {max_files})")

        # Stream each upload straight to a temp file (never the whole batch
        # in memory), enforcing the size cap as we go. The worker later
        # moves them into the job's run dir.
        staged: list[tuple[str, str]] = []  # (original name, temp path)
        total = 0
        try:
            for f in uploads:
                tmp = tempfile.NamedTemporaryFile(prefix="metascrub-up-", delete=False)
                try:
                    while chunk := await f.read(_CHUNK):
                        total += len(chunk)
                        if total > max_upload_bytes:
                            raise HTTPException(413, f"upload exceeds {max_upload_mb} MB")
                        tmp.write(chunk)
                finally:
                    tmp.close()
                staged.append((secure_filename(f.filename or "") or "file", tmp.name))
        except Exception:
            for _n, p in staged:
                _rm(p)
            raise

        def work(log, run_path: str) -> BatchReport:
            up_dir = os.path.join(run_path, "uploads")
            os.makedirs(up_dir, exist_ok=True)
            paths: list[str] = []
            for name, tmp_path in staged:
                dest = os.path.join(up_dir, name)
                stem, ext = os.path.splitext(dest)
                n = 1
                while dest in paths or os.path.exists(dest):
                    dest = f"{stem}({n}){ext}"
                    n += 1
                shutil.move(tmp_path, dest)
                paths.append(dest)
            cfg = CleanConfig(
                output_dir=os.path.join(run_path, "cleaned"),
                keep_fields=["Title"] if keep_title else [],
                keep_color_profile=keep_color_profile,
            )
            return clean_file_list(paths, cfg, base_dir=up_dir, log=log)

        try:
            job = store.submit(report_lang=report_lang if report_lang in ("en", "tr") else "en",
                               file_count=len(staged), work=work)
        except JobQueueFull as exc:
            for _n, p in staged:
                _rm(p)
            raise HTTPException(429, str(exc)) from exc

        return JobCreated(job_id=job.job_id, status="queued", run_id=job.run_id,
                          created_at=job.created_at.isoformat(), links=_links(request, job.job_id))

    @app.get("/v1/clean", response_model=list[JobStatusResponse], tags=["clean"], dependencies=guard)
    def list_jobs(request: Request) -> list[JobStatusResponse]:
        return [_status(j, request) for j in store.list()]

    @app.get("/v1/clean/{job_id}", response_model=JobStatusResponse, tags=["clean"], name="get_job", dependencies=guard)
    def get_job(job_id: str, request: Request) -> JobStatusResponse:
        return _status(_require(store, job_id), request)

    @app.get("/v1/clean/{job_id}/log", response_model=JobLogResponse, tags=["clean"], name="get_job_log", dependencies=guard)
    def get_job_log(job_id: str) -> JobLogResponse:
        job = _require(store, job_id)
        return JobLogResponse(job_id=job.job_id, status=job.status, lines=list(job.log_lines))

    @app.get("/v1/clean/{job_id}/report.json", tags=["clean"], name="get_job_report_json", dependencies=guard)
    def get_job_report_json(job_id: str) -> Response:
        job = _require_done(store, job_id)
        with open(os.path.join(job.run_path, "report.json"), encoding="utf-8") as fh:
            return Response(fh.read(), media_type="application/json")

    @app.get("/v1/clean/{job_id}/report.html", response_class=HTMLResponse, tags=["clean"],
             name="get_job_report_html", dependencies=guard)
    def get_job_report_html(job_id: str) -> str:
        job = _require_done(store, job_id)
        with open(os.path.join(job.run_path, "report.html"), encoding="utf-8") as fh:
            return fh.read()

    @app.get("/v1/clean/{job_id}/download", tags=["clean"], name="get_job_download", dependencies=guard)
    def get_job_download(job_id: str) -> StreamingResponse:
        job = _require_done(store, job_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            cleaned = os.path.join(job.run_path, "cleaned")
            for root, _, names in os.walk(cleaned):
                for name in names:
                    full = os.path.join(root, name)
                    zf.write(full, os.path.join("cleaned", os.path.relpath(full, cleaned)))
            for meta in ("report.json", "report.html"):
                p = os.path.join(job.run_path, meta)
                if os.path.isfile(p):
                    zf.write(p, meta)
        buf.seek(0)
        headers = {"Content-Disposition": f'attachment; filename="metascrub-{job.run_id}.zip"'}
        return StreamingResponse(buf, media_type="application/zip", headers=headers)

    return app
