from __future__ import annotations

from ..models import FieldChange
from .base import Engine, new_result
from .exiftool import exiftool_available, exiftool_version
from .image import ImageEngine
from .legacy_office import LegacyOfficeEngine
from .office import OfficeEngine
from .pdf import PdfEngine
from .svg import SvgEngine

__all__ = ["Engine", "engine_for", "supported_extensions", "missing_dependencies", "tool_versions"]


_REAL_ENGINES: tuple[Engine, ...] = (
    PdfEngine(), OfficeEngine(), LegacyOfficeEngine(), ImageEngine(), SvgEngine(),
)


def engine_for(ext: str) -> Engine | None:
    ext = ext.lower().lstrip(".")
    for engine in _REAL_ENGINES:
        if ext in engine.extensions:
            return engine  # type: ignore[return-value]
    return None


def supported_extensions() -> frozenset[str]:
    out: set[str] = set()
    for engine in _REAL_ENGINES:
        out |= set(engine.extensions)
    return frozenset(out)


def missing_dependencies(exts: set[str]) -> list[str]:
    """Human-readable list of things that need installing for the given
    set of file extensions to be scrubbable. Empty when everything's ready.
    """
    missing: list[str] = []
    if any(e in ImageEngine.extensions for e in exts) and not exiftool_available():
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
