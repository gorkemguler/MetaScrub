"""Recursively scrub the members of a `.zip` archive or the attachments of
an `.eml` email. Each member that MetaScrub understands is scrubbed with
the normal engine; everything else is copied through untouched. Opt-in
via `metascrub clean --recurse`.
"""
from __future__ import annotations

import dataclasses
import email
import email.policy
import os
import tempfile
import zipfile

from ..config import CONTAINER_EXTENSIONS, CleanConfig
from ..models import FieldChange
from .base import new_result

_MAX_DEPTH = 4
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


class ContainerEngine:
    name = "container"
    extensions = CONTAINER_EXTENSIONS

    def probe(self, path: str, cfg: CleanConfig | None = None) -> list[FieldChange]:
        ext = _ext(path)
        rows: list[FieldChange] = []
        try:
            if ext == "zip":
                for member, data in _zip_members(path):
                    rows += _member_rows(member, data)
            elif ext == "eml":
                for name, data in _eml_attachments(path):
                    rows += _member_rows(name, data)
        except Exception:  # noqa: BLE001 - unreadable container
            return rows
        return rows

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        ext = _ext(src)
        if cfg._recurse_depth >= _MAX_DEPTH:
            return new_result(src, None, self.name, "skipped",
                              reason=f"nested container past depth {_MAX_DEPTH}")
        removed: list[FieldChange] = []
        try:
            if ext == "zip":
                removed = _scrub_zip(src, dst, cfg)
            elif ext == "eml":
                removed = _scrub_eml(src, dst, cfg)
            else:
                return new_result(src, None, self.name, "unsupported", reason=f".{ext}")
        except Exception as exc:  # noqa: BLE001
            return new_result(src, None, self.name, "error", error=str(exc))
        return new_result(src, dst, self.name, "cleaned", removed=removed)


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
    with tempfile.TemporaryDirectory(prefix="metascrub-c-") as tmp:
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
