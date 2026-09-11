"""Recursively scrub the members of an archive or the attachments of an
email. Each member MetaCLS understands is scrubbed with the normal
engine; everything else is copied through untouched. Opt-in via
`metacls clean --recurse`.

Supported: `.zip`, `.eml` (stdlib); `.tar` and its compressed forms
`.tar.gz` / `.tgz` / `.tar.bz2` / `.tar.xz` (stdlib `tarfile`, which also
normalises the per-file uid/gid/uname/mtime headers — a leak of its own);
`.7z` (optional `py7zr`, `pip install 'metacls[archive]'`); `.msg`
(optional `extract-msg`, **read-only** — `probe` lists what's inside, but
rewriting an Outlook CFB is out of scope, so `strip` skips it).
"""
from __future__ import annotations

import dataclasses
import email
import email.policy
import os
import tarfile
import tempfile
import zipfile

from ..config import CONTAINER_EXTENSIONS, CleanConfig
from ..models import FieldChange
from .base import new_result

_MAX_DEPTH = 4
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

_TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tbz", ".tar.xz", ".txz")
_TAR_WRITE_MODE = {
    "gz": "w:gz", "tgz": "w:gz",
    "bz2": "w:bz2", "tbz2": "w:bz2", "tbz": "w:bz2",
    "xz": "w:xz", "txz": "w:xz",
}


class ContainerEngine:
    name = "container"
    extensions = CONTAINER_EXTENSIONS

    def probe(self, path: str, cfg: CleanConfig | None = None) -> list[FieldChange]:
        kind = _kind(path)
        rows: list[FieldChange] = []
        try:
            if kind == "zip":
                for member, data in _zip_members(path):
                    rows += _member_rows(member, data)
            elif kind == "eml":
                for name, data in _eml_attachments(path):
                    rows += _member_rows(name, data)
            elif kind == "tar":
                for name, data in _tar_members(path):
                    rows += _member_rows(name, data)
            elif kind == "7z":
                for name, data in _sevenz_members(path):
                    rows += _member_rows(name, data)
            elif kind == "msg":
                rows += _msg_rows(path)
        except Exception:  # noqa: BLE001 - unreadable container
            return rows
        return rows

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        kind = _kind(src)
        if cfg._recurse_depth >= _MAX_DEPTH:
            return new_result(src, None, self.name, "skipped",
                              reason=f"nested container past depth {_MAX_DEPTH}")
        if kind == "msg":
            return new_result(src, None, self.name, "skipped",
                              reason=".msg is read-only — inspect --recurse lists it; export to .eml to scrub")
        if kind == "7z" and not _have_py7zr():
            return new_result(src, None, self.name, "skipped",
                              reason="need py7zr for .7z — pip install 'metacls[archive]'")
        removed: list[FieldChange] = []
        try:
            if kind == "zip":
                removed = _scrub_zip(src, dst, cfg)
            elif kind == "eml":
                removed = _scrub_eml(src, dst, cfg)
            elif kind == "tar":
                removed = _scrub_tar(src, dst, cfg)
            elif kind == "7z":
                removed = _scrub_7z(src, dst, cfg)
            else:
                return new_result(src, None, self.name, "unsupported", reason=f".{_ext(src)}")
        except Exception as exc:  # noqa: BLE001
            return new_result(src, None, self.name, "error", error=str(exc))
        return new_result(src, dst, self.name, "cleaned", removed=removed)


# --- kind detection -----------------------------------------------------------


def _kind(path: str) -> str:
    low = os.path.basename(path).lower()
    if low.endswith(".zip"):
        return "zip"
    if low.endswith(".eml"):
        return "eml"
    if low.endswith(".msg"):
        return "msg"
    if low.endswith(".7z"):
        return "7z"
    if low.endswith(_TAR_SUFFIXES):
        return "tar"
    # bare .gz / .bz2 / .xz: a container only if it's actually a tar
    if low.endswith((".gz", ".bz2", ".xz")):
        try:
            if tarfile.is_tarfile(path):
                return "tar"
        except (OSError, tarfile.TarError):
            return ""
    return ""


# --- zip -------------------------------------------------------------------


def _zip_members(path: str):
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            yield info.filename, zf.read(info)


def _scrub_zip(src: str, dst: str, cfg: CleanConfig) -> list[FieldChange]:
    removed: list[FieldChange] = []
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.is_dir():
                continue
            data = zin.read(info)
            new_data, member_removed = _scrub_bytes(info.filename, data, cfg)
            removed += member_removed
            ni = zipfile.ZipInfo(info.filename, date_time=_ZIP_EPOCH)
            ni.compress_type = zipfile.ZIP_DEFLATED
            ni.external_attr = info.external_attr
            zout.writestr(ni, new_data)
    return removed


# --- tar (+ gz / bz2 / xz) ------------------------------------------------


def _tar_members(path: str):
    with tarfile.open(path, "r:*") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            f = tf.extractfile(m)
            if f is None:
                continue
            yield m.name, f.read()


def _tar_write_mode(path: str):
    from typing import Literal, cast

    return cast('Literal["w", "w:gz", "w:bz2", "w:xz"]', _TAR_WRITE_MODE.get(_ext(path), "w"))


def _scrub_tar(src: str, dst: str, cfg: CleanConfig) -> list[FieldChange]:
    removed: list[FieldChange] = []
    with tarfile.open(src, "r:*") as tin, tarfile.open(dst, _tar_write_mode(src)) as tout:
        for m in tin.getmembers():
            if m.isfile():
                f = tin.extractfile(m)
                data = f.read() if f is not None else b""
                new_data, member_removed = _scrub_bytes(m.name, data, cfg)
                removed += member_removed
            elif m.isdir():
                new_data = b""
            else:
                # symlink / device / fifo — keep the entry, no payload
                tout.addfile(_clean_tarinfo(m))
                continue
            ti = _clean_tarinfo(m)
            ti.size = len(new_data)
            tout.addfile(ti, fileobj=_bytesio(new_data) if new_data else None)
    if not removed:
        # still rewrote the tar to normalise uid/gid/mtime headers
        removed.append(FieldChange("tar", "member headers",
                                   "<uid/gid/uname/gname/mtime>", after="<normalised>"))
    return removed


def _clean_tarinfo(m: tarfile.TarInfo) -> tarfile.TarInfo:
    """A copy of the member's header with the packer's identity / clock
    zeroed — tar leaks the uid, username and mtime of whoever made it."""
    ti = tarfile.TarInfo(m.name)
    ti.type = m.type
    ti.mode = m.mode & 0o777
    ti.linkname = m.linkname
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    ti.mtime = 0
    return ti


def _bytesio(data: bytes):
    import io

    return io.BytesIO(data)


# --- 7z (optional py7zr) -------------------------------------------------


def _have_py7zr() -> bool:
    try:
        import py7zr  # noqa: F401

        return True
    except ImportError:
        return False


def _sevenz_extract(path: str, into: str) -> list[str]:
    """Extract `path` under `into` and return the member names (posix
    separators), sorted. py7zr's in-memory read API was removed in 1.x,
    so it goes via the filesystem."""
    import py7zr

    with py7zr.SevenZipFile(path, "r") as z:
        z.extractall(path=into)
    names: list[str] = []
    for root, _dirs, files in os.walk(into):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), into)
            names.append(rel.replace(os.sep, "/"))
    names.sort()
    return names


def _sevenz_members(path: str):
    with tempfile.TemporaryDirectory(prefix="metacls-7z-") as tmp:
        for rel in _sevenz_extract(path, tmp):
            with open(os.path.join(tmp, rel.replace("/", os.sep)), "rb") as fh:
                yield rel, fh.read()


def _scrub_7z(src: str, dst: str, cfg: CleanConfig) -> list[FieldChange]:
    import py7zr

    removed: list[FieldChange] = []
    with tempfile.TemporaryDirectory(prefix="metacls-7z-") as tmp:
        names = _sevenz_extract(src, tmp)
        with py7zr.SevenZipFile(dst, "w") as zout:
            for rel in names:
                with open(os.path.join(tmp, rel.replace("/", os.sep)), "rb") as fh:
                    data = fh.read()
                new_data, member_removed = _scrub_bytes(rel, data, cfg)
                removed += member_removed
                zout.writef(_bytesio(new_data), rel)  # parent dirs are implicit
    return removed


# --- msg (optional extract-msg, read-only) ------------------------------


def _msg_rows(path: str) -> list[FieldChange]:
    try:
        import extract_msg
    except ImportError:
        return [FieldChange("msg", "note", "install extract-msg to inspect .msg — pip install 'metacls[msg]'")]
    rows: list[FieldChange] = []
    msg = extract_msg.Message(path)
    try:
        for field in ("sender", "to", "cc", "date", "subject"):
            val = getattr(msg, field, None)
            if val:
                rows.append(FieldChange("msg header", field, str(val)[:200]))
        for att in msg.attachments:
            name = getattr(att, "longFilename", None) or getattr(att, "shortFilename", None) or "attachment"
            data = getattr(att, "data", None)
            if isinstance(data, (bytes, bytearray)) and data:
                rows += _member_rows(str(name), bytes(data))
    finally:
        try:
            msg.close()
        except Exception:  # noqa: BLE001
            pass
    return rows


# --- eml -----------------------------------------------------------------


def _eml_attachments(path: str):
    with open(path, "rb") as fh:
        msg = email.message_from_binary_file(fh, policy=email.policy.default)
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        name = part.get_filename() or "attachment"
        payload = part.get_payload(decode=True)
        if isinstance(payload, (bytes, bytearray)) and payload:
            yield name, bytes(payload)


def _scrub_eml(src: str, dst: str, cfg: CleanConfig) -> list[FieldChange]:
    with open(src, "rb") as fh:
        msg = email.message_from_binary_file(fh, policy=email.policy.default)
    removed: list[FieldChange] = []
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        name = part.get_filename() or "attachment"
        payload = part.get_payload(decode=True)
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            continue
        new_payload, part_removed = _scrub_bytes(name, bytes(payload), cfg)
        if new_payload != payload:
            part.set_payload(new_payload)
            _reencode(part)
            removed += part_removed
    with open(dst, "wb") as fh:
        fh.write(msg.as_bytes())
    return removed


def _reencode(part) -> None:
    # set_payload with raw bytes needs the transfer encoding re-applied.
    del part["Content-Transfer-Encoding"]
    try:
        import email.encoders

        email.encoders.encode_base64(part)
    except Exception:  # noqa: BLE001
        pass


# --- shared --------------------------------------------------------------


def _scrub_bytes(member_name: str, data: bytes, cfg: CleanConfig) -> tuple[bytes, list[FieldChange]]:
    """Scrub one member's bytes with the matching engine. Returns
    (possibly-unchanged bytes, FieldChanges prefixed with the member name).
    """
    from . import engine_for  # local import: avoids an import cycle

    ext = _ext(member_name)
    engine = engine_for(ext)
    if engine is None:
        return data, []

    child_cfg = dataclasses.replace(cfg, in_place=False, quarantine=None, jobs=1,
                                    _recurse_depth=cfg._recurse_depth + 1)
    with tempfile.TemporaryDirectory(prefix="metacls-c-") as tmp:
        in_path = os.path.join(tmp, os.path.basename(member_name) or f"m.{ext}")
        with open(in_path, "wb") as fh:
            fh.write(data)
        out_path = in_path + ".out"
        result = engine.strip(in_path, out_path, child_cfg)
        if result.status != "cleaned" or not result.out_path or not os.path.isfile(result.out_path):
            return data, []
        with open(result.out_path, "rb") as fh:
            new_data = fh.read()
    rows = [FieldChange(f"{member_name} · {fc.namespace}", fc.field, fc.before) for fc in result.removed]
    return new_data, rows


def _member_rows(member_name: str, data: bytes) -> list[FieldChange]:
    from . import engine_for

    engine = engine_for(_ext(member_name))
    if engine is None:
        return []
    try:
        with tempfile.NamedTemporaryFile(suffix="." + _ext(member_name), delete=False) as tf:
            tf.write(data)
            tmp = tf.name
        rows = [FieldChange(f"{member_name} · {fc.namespace}", fc.field, fc.before)
                for fc in engine.probe(tmp)]
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return rows


def _ext(path: str) -> str:
    base = os.path.basename(path)
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""
