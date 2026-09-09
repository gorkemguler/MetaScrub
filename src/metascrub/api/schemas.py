from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    active_jobs: int


class JobSummary(BaseModel):
    files: int
    by_status: dict[str, int]
    fields_removed: int
    files_with_residual: int
    files_errored: int


class JobLinks(BaseModel):
    self: str
    log: str
    report_json: str
    report_html: str
    download: str


class JobCreated(BaseModel):
    job_id: str
    status: str
    run_id: str
    created_at: str
    links: JobLinks


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    run_id: str
    file_count: int
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    summary: JobSummary | None = None
    links: JobLinks


class JobLogResponse(BaseModel):
    job_id: str
    status: str
    lines: list[str]


class FieldChangeOut(BaseModel):
    namespace: str
    field: str
    before: str
    after: str | None = None


class FileResultOut(BaseModel):
    src_path: str
    out_path: str | None
    filetype: str
    engine: str
    status: str
    reason: str | None = None
    error: str | None = None
    bytes_before: int
    bytes_after: int
    kept: list[str]
    residual: list[str]
    removed: list[FieldChangeOut]
