from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class FieldChange:
    """One metadata field the scrub touched (or would touch, in dry-run).

    `after is None` means the field was removed outright — the common case
    for an aggressive strip. A non-None `after` is a field that was reset
    to a neutral/empty value rather than deleted (some OOXML fields have to
    stay present but blank for the file to remain valid).
    """

    namespace: str  # "PDF Info" | "XMP" | "docProps/core" | "docProps/app" | "EXIF" | "GPS" | ...
    field: str      # leaf name: "Author", "Producer", "dc:creator", "GPSLatitude"
    before: str
    after: str | None = None


@dataclass
class CleanResult:
    """Outcome of scrubbing a single file."""

    src_path: str
    filetype: str
    engine: str                 # "pdf" | "office" | "image"
    status: str                 # "cleaned" | "skipped" | "unsupported" | "error"
    out_path: str | None = None
    removed: list[FieldChange] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)      # field names deliberately preserved
    residual: list[str] = field(default_factory=list)  # metadata still present after cleaning (verify pass)
    bytes_before: int = 0
    bytes_after: int = 0
    reason: str | None = None    # why it was skipped/unsupported (e.g. "signed PDF")
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("cleaned", "skipped", "unsupported") and self.error is None

    @property
    def has_residual(self) -> bool:
        return bool(self.residual)


@dataclass
class BatchReport:
    """Result of one `metacls clean` / web / API run over many files."""

    root: str = ""              # directory scanned, or "<uploads>" for web/API
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    in_place: bool = False
    dry_run: bool = False
    results: list[CleanResult] = field(default_factory=list)
    tool_versions: dict[str, str] = field(default_factory=dict)  # metacls / pikepdf / exiftool

    # --- convenience aggregates (used by the CLI table, reports, API summary) ---

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    @property
    def fields_removed(self) -> int:
        return sum(len(r.removed) for r in self.results)

    @property
    def files_with_residual(self) -> list[CleanResult]:
        return [r for r in self.results if r.has_residual]

    @property
    def errored(self) -> list[CleanResult]:
        return [r for r in self.results if r.status == "error"]
