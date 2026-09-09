from __future__ import annotations

from ..config import LEGACY_OFFICE_EXTENSIONS
from ..models import FieldChange
from .base import Engine, new_result
from .exiftool import exiftool_available, exiftool_version
from .image import ImageEngine
from .office import OfficeEngine
from .pdf import PdfEngine

__all__ = ["Engine", "engine_for", "supported_extensions", "missing_dependencies"]


class _UnsupportedEngine:
    """Stand-in for a recognised-but-not-scrubbable format. Reports the
    file so it shows up in the run, but writes nothing.
    """

    name = "office"

    def __init__(self, extensions: frozenset[str], reason: str) -> None:
        self.extensions = extensions
        self._reason = reason

    def probe(self, path: str) -> list[FieldChange]:
        return []

    def strip(self, src: str, dst: str, cfg):
        return new_result(src, None, self.name, "unsupported", reason=self._reason)


_LEGACY_OFFICE = _UnsupportedEngine(
    LEGACY_OFFICE_EXTENSIONS,
    "legacy OLE2 format (.doc/.xls/.ppt) — convert to .docx/.xlsx/.pptx first",
)

_REAL_ENGINES: tuple[Engine, ...] = (PdfEngine(), OfficeEngine(), ImageEngine())
_ALL_ENGINES: tuple[object, ...] = (*_REAL_ENGINES, _LEGACY_OFFICE)


def engine_for(ext: str) -> Engine | None:
    ext = ext.lower().lstrip(".")
    for engine in _ALL_ENGINES:
        if ext in engine.extensions:
            return engine  # type: ignore[return-value]
    return None


def supported_extensions() -> frozenset[str]:
    out: set[str] = set()
    for engine in _ALL_ENGINES:
        out |= set(engine.extensions)
    return frozenset(out)


def missing_dependencies(exts: set[str]) -> list[str]:
    """Human-readable list of things that need installing for the given
    set of file extensions to be scrubbable. Empty when everything's ready.
    """
    missing: list[str] = []
    needs_exiftool = any(e in ImageEngine.extensions for e in exts)
    if needs_exiftool and not exiftool_available():
        missing.append(
            "exiftool binary (image scrubbing) — `brew install exiftool` (macOS) "
            "or `apt install libimage-exiftool-perl` (Debian/Ubuntu). "
            "Without it MetaScrub falls back to Pillow, if installed, for jpg/png only."
        )
    return missing


def tool_versions() -> dict[str, str]:
    from .. import __version__

    versions = {"metascrub": __version__}
    try:
        import pikepdf

        versions["pikepdf"] = pikepdf.__version__
    except Exception:  # noqa: BLE001
        pass
    ev = exiftool_version()
    if ev:
        versions["exiftool"] = ev
    return versions
