from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from ..config import CleanConfig
from ..models import CleanResult, FieldChange


@runtime_checkable
class Engine(Protocol):
    """A format-specific metadata scrubber.

    `probe` is read-only: it returns the metadata currently in the file as
    a list of FieldChange rows with `after` unset — the "before" view used
    by `metascrub inspect`, by dry-run, and by the verify pass (where a
    non-empty result means residual metadata survived).

    `strip` writes a cleaned copy of `src` to `dst` and returns a
    CleanResult describing what it removed. It must not modify `src`.
    """

    name: str
    extensions: frozenset[str]

    def probe(self, path: str) -> list[FieldChange]: ...

    def strip(self, src: str, dst: str, cfg: CleanConfig) -> CleanResult: ...


def new_result(src: str, dst: str | None, engine: str, status: str, **kw) -> CleanResult:
    """Build a CleanResult with byte sizes filled in from disk."""
    bytes_before = _safe_size(src)
    bytes_after = _safe_size(dst) if dst else 0
    return CleanResult(
        src_path=src,
        out_path=dst,
        filetype=_ext(src),
        engine=engine,
        status=status,
        bytes_before=bytes_before,
        bytes_after=bytes_after,
        **kw,
    )


def _safe_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _ext(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in os.path.basename(path) else ""
