from __future__ import annotations

import datetime as _dt
import os
import shutil
import subprocess
import tempfile

import olefile

from ..config import CleanConfig, LEGACY_OFFICE_EXTENSIONS
from ..models import FieldChange
from .base import new_result
from .office import OfficeEngine

# OleMetadata attributes that identify a person / org / machine, as
# opposed to counts and structural flags. Reported by probe(); all of them
# are gone after the LibreOffice round-trip through OOXML.
_SUMMARY_IDENTITY = (
    "title", "subject", "author", "keywords", "comments", "template",
    "last_saved_by", "revision_number", "total_edit_time", "last_printed",
    "create_time", "last_saved_time", "creating_application",
)
_DOCSUM_IDENTITY = ("category", "manager", "company", "content_status", "link_base")

_CONVERT_TARGET = {"doc": "docx", "xls": "xlsx", "ppt": "pptx"}


def soffice_path() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


class LegacyOfficeEngine:
    """Legacy OLE2 formats (.doc / .xls / .ppt). `olefile` can only *read*
    a compound file, so there's no in-place strip: scrubbing means
    converting to the modern OOXML format with LibreOffice and running the
    normal office scrubber over the result. Without `soffice` on PATH the
    file is reported `unsupported`.
    """

    name = "office"
    extensions = LEGACY_OFFICE_EXTENSIONS

    def probe(self, path: str, cfg: CleanConfig | None = None) -> list[FieldChange]:
        if not olefile.isOleFile(path):
            return []
        rows: list[FieldChange] = []
        try:
            with olefile.OleFileIO(path) as ole:
                meta = ole.get_metadata()
                cp = getattr(meta, "codepage", None)
                for attr in _SUMMARY_IDENTITY:
                    rows.extend(_row("SummaryInformation", attr, getattr(meta, attr, None), cp))
                for attr in _DOCSUM_IDENTITY:
                    rows.extend(_row("DocumentSummaryInformation", attr, getattr(meta, attr, None), cp))
                if getattr(meta, "thumbnail", None):
                    rows.append(FieldChange("SummaryInformation", "thumbnail", "<embedded preview image>"))
        except Exception:  # noqa: BLE001 - olefile raises assorted errors on malformed files
            return rows
        return rows

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        ext = _ext(src)
        target = _CONVERT_TARGET.get(ext)
        if target is None:
            return new_result(src, None, self.name, "unsupported",
                              reason=f"unsupported legacy format '.{ext}'")

        if cfg.in_place:
            return new_result(
                src, None, self.name, "skipped",
                reason=f"legacy .{ext} can't be scrubbed in place — the format changes to .{target}; "
                       "run without --in-place",
            )

        soffice = soffice_path()
        if soffice is None:
            return new_result(
                src, None, self.name, "unsupported",
                reason=f"legacy OLE2 .{ext} — install LibreOffice (soffice) to auto-convert and "
                       f"scrub, or convert to .{target} yourself first",
            )

        before = self.probe(src)
        # We invent the output name (extension changes), so make sure its
        # directory exists rather than relying on the caller having created
        # it for the original path.
        out_path = os.path.splitext(dst)[0] + "." + target
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="metascrub-lo-") as tmp:
            converted = _libreoffice_convert(soffice, src, target, tmp)
            if converted is None or not os.path.isfile(converted):
                return new_result(src, None, self.name, "error",
                                  error="LibreOffice conversion produced no output")
            inner = OfficeEngine().strip(converted, out_path, cfg)

        if inner.status != "cleaned":
            inner.src_path = src
            inner.reason = inner.reason or "LibreOffice conversion + scrub failed"
            return inner

        result = new_result(src, out_path, self.name, "cleaned",
                            removed=before or inner.removed, kept=inner.kept)
        result.residual = inner.residual
        result.reason = f"converted to .{target} and scrubbed via LibreOffice"
        return result


def _libreoffice_convert(soffice: str, src: str, target: str, outdir: str) -> str | None:
    # Own UserInstallation profile so this doesn't clash with a LibreOffice
    # the user already has open (soffice is otherwise single-instance).
    profile = os.path.join(outdir, "loprofile")
    cmd = [
        soffice, "--headless", "--norestore", "--nolockcheck",
        f"-env:UserInstallation=file://{profile}",
        "--convert-to", target, "--outdir", outdir, src,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    produced = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + "." + target)
    return produced if os.path.isfile(produced) else None


# FILETIME 0 -> this datetime; OLE uses it for "unset", not a real date.
_OLE_NULL_DATE = _dt.datetime(1601, 1, 1)

# Codepage id -> Python codec, for the handful that actually show up.
_CODEPAGE = {65001: "utf-8", 1252: "cp1252", 1251: "cp1251", 1254: "cp1254",
             1250: "cp1250", 1253: "cp1253", 932: "cp932", 936: "gbk", 949: "cp949"}


def _row(namespace: str, attr: str, value, codepage=None) -> list[FieldChange]:
    if value is None:
        return []
    if isinstance(value, bytes):
        codec = _CODEPAGE.get(codepage, "cp1252")
        value = value.decode(codec, errors="replace").strip()
    if isinstance(value, _dt.datetime):
        if value.replace(tzinfo=None) == _OLE_NULL_DATE:
            return []
        value = value.isoformat(sep=" ")
    text = str(value).strip()
    if text in ("", "0"):
        return []
    return [FieldChange(namespace, attr, text)]


def _ext(path: str) -> str:
    base = os.path.basename(path)
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""
