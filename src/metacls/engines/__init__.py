from __future__ import annotations

from .base import Engine
from .exiftool import exiftool_available, exiftool_version
from .image import ImageEngine
from .legacy_office import LegacyOfficeEngine
from .media import MediaEngine
from .office import OfficeEngine
from .pdf import PdfEngine
from .svg import SvgEngine

__all__ = ["Engine", "engine_for", "supported_extensions", "missing_dependencies",
           "tool_versions", "format_support"]

# Imported lazily inside engine_for to avoid an import cycle
# (container.py -> engines/__init__ -> container.py).
_container_engine = None


def _get_container_engine():
    global _container_engine
    if _container_engine is None:
        from .container import ContainerEngine

        _container_engine = ContainerEngine()
    return _container_engine


_REAL_ENGINES: tuple[Engine, ...] = (
    PdfEngine(), OfficeEngine(), LegacyOfficeEngine(), ImageEngine(), SvgEngine(), MediaEngine(),
)


def engine_for(ext: str) -> Engine | None:
    ext = ext.lower().lstrip(".")
    for engine in _REAL_ENGINES:
        if ext in engine.extensions:
            return engine
    if ext in _get_container_engine().extensions:
        return _get_container_engine()
    return None


def supported_extensions() -> frozenset[str]:
    out: set[str] = set()
    for engine in _REAL_ENGINES:
        out |= set(engine.extensions)
    return frozenset(out | _get_container_engine().extensions)


def _module_present(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def format_support() -> dict:
    """A machine-readable summary of what MetaCLS can scrub right now:
    extensions per engine, and which optional pieces are installed. Drives
    `GET /v1/formats` and the web UI's format hint.
    """
    from .exiftool import exiftool_available

    engines = {e.name: sorted(e.extensions) for e in _REAL_ENGINES}
    engines[_get_container_engine().name] = sorted(_get_container_engine().extensions)
    optional = {
        "exiftool": exiftool_available(),          # images + mp4-family video
        "libreoffice": _soffice_present(),         # legacy .doc/.xls/.ppt fallback
        "mutagen": _module_present("mutagen"),     # audio tags
        "pillow": _module_present("PIL"),          # image fallback when exiftool is absent
        "py7zr": _module_present("py7zr"),         # .7z recursion
        "extract_msg": _module_present("extract_msg"),  # .msg inspection
    }
    return {
        "extensions": sorted(supported_extensions()),
        "engines": engines,
        "optional": optional,
        "tool_versions": tool_versions(),
    }


def _soffice_present() -> bool:
    from .legacy_office import soffice_path

    return soffice_path() is not None


def missing_dependencies(exts: set[str]) -> list[str]:
    """Human-readable list of things that need installing for the given
    set of file extensions to be scrubbable. Empty when everything's ready.
    """
    missing: list[str] = []
    if any(e in ImageEngine.extensions for e in exts) and not exiftool_available():
        missing.append(
            "exiftool binary (image scrubbing) — `brew install exiftool` (macOS) "
            "or `apt install libimage-exiftool-perl` (Debian/Ubuntu). "
            "Without it MetaCLS falls back to Pillow, if installed, for jpg/png only."
        )
    return missing


def tool_versions() -> dict[str, str]:
    from .. import __version__

    versions = {"metacls": __version__}
    for mod in ("pikepdf", "olefile", "mutagen", "PIL"):
        try:
            m = __import__(mod)
            label = "pillow" if mod == "PIL" else mod
            ver = getattr(m, "__version__", None) or getattr(m, "version_string", None)
            versions[label] = str(ver or "?")
        except Exception:  # noqa: BLE001
            pass
    ev = exiftool_version()
    if ev:
        versions["exiftool"] = ev
    from .legacy_office import soffice_path

    sp = soffice_path()
    if sp:
        # Path, not a version: `soffice --version` spins up a full LO
        # process (~1 s) and this is called on every run.
        versions["libreoffice"] = sp
    return versions
