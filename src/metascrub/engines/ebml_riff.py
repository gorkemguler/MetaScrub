"""In-place metadata scrubbing for the two video containers exiftool
can't write: Matroska / WebM (EBML) and AVI (RIFF).

Both work the same way — the file length never changes, so `--in-place`
is trivial and the output is deterministic:

* **Matroska / WebM** — the whole ``Tags`` element (TITLE, ARTIST,
  COMMENT, ENCODER, dates, …) is overwritten with an EBML ``Void``
  element of identical length; ``Info``'s ``Title`` and ``DateUTC`` are
  voided too, and ``MuxingApp`` / ``WritingApp`` (the muxer/writer
  software names) have their string payload zeroed. Every Matroska
  parser skips ``Void``.
* **AVI** — a ``LIST INFO`` chunk (INAM/IART/ICMT/ISFT/ICRD/…) and a
  top-level or ``hdrl`` ``IDIT`` chunk are relabelled ``JUNK`` and their
  payload zeroed. Every RIFF reader skips ``JUNK``.

The track data, timestamps and codec headers are never touched.
"""
from __future__ import annotations

# --- EBML (Matroska / WebM) ------------------------------------------------

_EBML_HEADER = 0x1A45DFA3
_ID_SEGMENT = 0x18538067
_ID_INFO = 0x1549A966
_ID_TAGS = 0x1254C367
_ID_ATTACHMENTS = 0x1941A469  # not touched (files), listed for readability

_INFO_VOID = {0x7BA9: "Title", 0x4461: "DateUTC"}
_INFO_BLANK = {0x4D80: "MuxingApp", 0x5741: "WritingApp"}

# SimpleTag children
_ID_TAG = 0x7373
_ID_SIMPLE_TAG = 0x67C8
_ID_TAG_NAME = 0x45A3
_ID_TAG_STRING = 0x4487


def _read_vint(buf: bytes, pos: int, *, keep_marker: bool) -> tuple[int, int]:
    """Decode one EBML variable-length integer at `buf[pos]`.

    Returns (value, byte length). For element IDs `keep_marker` is True —
    the marker bits are part of the canonical ID (e.g. 0x1254C367).
    """
    if pos >= len(buf):
        raise ValueError("truncated vint")
    first = buf[pos]
    if first == 0:
        raise ValueError("invalid vint length")
    length = 1
    mask = 0x80
    while not first & mask:
        mask >>= 1
        length += 1
        if length > 8:
            raise ValueError("vint too long")
    if pos + length > len(buf):
        raise ValueError("truncated vint")
    if keep_marker:
        return int.from_bytes(buf[pos : pos + length], "big"), length
    value = first & (mask - 1)
    all_ones = mask - 1
    for i in range(1, length):
        value = (value << 8) | buf[pos + i]
        all_ones = (all_ones << 8) | 0xFF
    if value == all_ones:
        return -1, length  # "unknown size"
    return value, length


def _void_bytes(n: int) -> bytes:
    """An EBML Void element (`0xEC`) whose total length is exactly n (>= 2)."""
    if n < 2:
        raise ValueError("cannot void < 2 bytes")
    for size_len in range(1, 9):
        max_v = (1 << (7 * size_len)) - 2
        body = n - 1 - size_len
        if 0 <= body <= max_v:
            marker = 0x80 >> (size_len - 1)
            top = body >> (8 * (size_len - 1))
            rest = (body & ((1 << (8 * (size_len - 1))) - 1)).to_bytes(size_len - 1, "big")
            return b"\xec" + bytes([marker | top]) + rest + b"\x00" * body
    raise ValueError("element too large to void")


def _walk(buf: bytes, start: int, end: int):
    """Yield (elem_start, elem_id, data_start, data_end) for each direct
    child element in buf[start:end]."""
    pos = start
    while pos + 1 < end:
        try:
            elem_id, id_len = _read_vint(buf, pos, keep_marker=True)
            size_val, size_len = _read_vint(buf, pos + id_len, keep_marker=False)
        except ValueError:
            return
        data_start = pos + id_len + size_len
        data_end = end if size_val < 0 else data_start + size_val
        if data_end > end or data_end <= pos:
            return
        yield pos, elem_id, data_start, data_end
        pos = data_end


def _segment_span(buf: bytes) -> tuple[int, int] | None:
    if len(buf) < 4 or int.from_bytes(buf[0:4], "big") != _EBML_HEADER:
        return None
    for _s, elem_id, ds, de in _walk(buf, 0, len(buf)):
        if elem_id == _ID_SEGMENT:
            return ds, de
    return None


def _tag_strings(buf: bytes, start: int, end: int) -> list[str]:
    names: list[str] = []
    for _s, eid, ds, de in _walk(buf, start, end):
        if eid in (_ID_TAG, _ID_SIMPLE_TAG):
            names.extend(_tag_strings(buf, ds, de))
        elif eid == _ID_TAG_NAME:
            try:
                names.append(buf[ds:de].decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
    return names


def _probe_matroska_buf(buf: bytes) -> list[tuple[str, str]]:
    span = _segment_span(buf)
    if span is None:
        return []
    seg_start, seg_end = span
    rows: list[tuple[str, str]] = []
    for _s, eid, ds, de in _walk(buf, seg_start, seg_end):
        if eid == _ID_TAGS:
            found = _tag_strings(buf, ds, de)
            rows.append(("Tags", ", ".join(sorted(set(found))) or "<tag block>"))
        elif eid == _ID_INFO:
            for _s2, ceid, cds, cde in _walk(buf, ds, de):
                if ceid == 0x4461:  # DateUTC — 8-byte signed int, ns since 2001
                    if any(buf[cds:cde]):
                        rows.append(("Info DateUTC", "<timestamp>"))
                    continue
                label = _INFO_VOID.get(ceid) or _INFO_BLANK.get(ceid)
                if label:
                    text = buf[cds:cde].split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
                    if text:
                        rows.append((f"Info {label}", text))
    return rows


def probe_matroska(path: str) -> list[tuple[str, str]]:
    try:
        with open(path, "rb") as fh:
            return _probe_matroska_buf(fh.read())
    except OSError:
        return []


def scrub_matroska(src: str, dst: str) -> tuple[bool, list[tuple[str, str]]]:
    try:
        with open(src, "rb") as fh:
            buf = bytearray(fh.read())
    except OSError as exc:
        return False, [("error", str(exc))]

    span = _segment_span(bytes(buf))
    if span is None:
        return False, [("error", "not a Matroska/WebM file")]
    seg_start, seg_end = span

    removed: list[tuple[str, str]] = []
    for s, eid, ds, de in _walk(bytes(buf), seg_start, seg_end):
        if eid == _ID_TAGS:
            found = _tag_strings(bytes(buf), ds, de)
            removed.append(("Tags", ", ".join(sorted(set(found))) or "<tag block>"))
            buf[s:de] = _void_bytes(de - s)
        elif eid == _ID_INFO:
            for cs, ceid, cds, cde in _walk(bytes(buf), ds, de):
                if ceid in _INFO_VOID:
                    removed.append((f"Info {_INFO_VOID[ceid]}", _preview(buf[cds:cde])))
                    buf[cs:cde] = _void_bytes(cde - cs)
                elif ceid in _INFO_BLANK:
                    removed.append((f"Info {_INFO_BLANK[ceid]}",
                                    buf[cds:cde].decode("utf-8", "replace") or "<set>"))
                    buf[cds:cde] = b"\x00" * (cde - cds)

    if not removed:
        return _copy(src, dst), []
    try:
        with open(dst, "wb") as fh:
            fh.write(buf)
    except OSError as exc:
        return False, [("error", str(exc))]
    return True, removed


# --- RIFF (AVI) ----------------------------------------------------------------

_INFO_TAGS = {
    b"INAM": "Title", b"IART": "Artist", b"ICMT": "Comment", b"ISFT": "Software",
    b"ICRD": "DateCreated", b"ICOP": "Copyright", b"IENG": "Engineer", b"IGNR": "Genre",
    b"ISRC": "Source", b"ISBJ": "Subject", b"IKEY": "Keywords", b"IPRD": "Product",
    b"ICMS": "Commissioned", b"IARL": "ArchivalLocation", b"ITCH": "Technician",
}
_RIFF_DESCEND = {b"hdrl", b"strl", b"odml"}


def _iter_riff(buf: bytes, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        fourcc = bytes(buf[pos : pos + 4])
        size = int.from_bytes(buf[pos + 4 : pos + 8], "little")
        body = pos + 8
        if body + size > end:
            return
        yield pos, fourcc, body, size
        pos = body + size + (size & 1)  # chunks are word-aligned


def _read_info_chunk(buf: bytes, start: int, end: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for _p, fourcc, body, size in _iter_riff(buf, start, end):
        label = _INFO_TAGS.get(fourcc)
        if label:
            rows.append((label, _preview(buf[body : body + size])))
    return rows


def _riff_span(buf: bytes) -> tuple[int, int] | None:
    if len(buf) < 12 or buf[0:4] != b"RIFF" or buf[8:12] != b"AVI ":
        return None
    total = int.from_bytes(buf[4:8], "little")
    return 12, min(len(buf), 8 + total)


def _walk_riff_for_meta(buf: bytearray, start: int, end: int,
                        removed: list[tuple[str, str]], *, mutate: bool) -> None:
    for pos, fourcc, body, size in _iter_riff(bytes(buf), start, end):
        if fourcc == b"LIST":
            form = bytes(buf[body : body + 4])
            if form == b"INFO":
                removed.extend(_read_info_chunk(bytes(buf), body + 4, body + size))
                if mutate:
                    buf[pos : pos + 4] = b"JUNK"
                    buf[body : body + size] = b"\x00" * size
            elif form in _RIFF_DESCEND:
                _walk_riff_for_meta(buf, body + 4, body + size, removed, mutate=mutate)
        elif fourcc == b"IDIT":
            removed.append(("IDIT", _preview(buf[body : body + size])))
            if mutate:
                buf[pos : pos + 4] = b"JUNK"
                buf[body : body + size] = b"\x00" * size


def probe_avi(path: str) -> list[tuple[str, str]]:
    try:
        with open(path, "rb") as fh:
            buf = bytearray(fh.read())
    except OSError:
        return []
    span = _riff_span(bytes(buf))
    if span is None:
        return []
    rows: list[tuple[str, str]] = []
    _walk_riff_for_meta(buf, span[0], span[1], rows, mutate=False)
    return rows


def scrub_avi(src: str, dst: str) -> tuple[bool, list[tuple[str, str]]]:
    try:
        with open(src, "rb") as fh:
            buf = bytearray(fh.read())
    except OSError as exc:
        return False, [("error", str(exc))]
    span = _riff_span(bytes(buf))
    if span is None:
        return False, [("error", "not an AVI (RIFF) file")]
    removed: list[tuple[str, str]] = []
    _walk_riff_for_meta(buf, span[0], span[1], removed, mutate=True)
    if not removed:
        return _copy(src, dst), []
    try:
        with open(dst, "wb") as fh:
            fh.write(buf)
    except OSError as exc:
        return False, [("error", str(exc))]
    return True, removed


# --- shared ------------------------------------------------------------------


def _preview(raw: bytes | bytearray) -> str:
    text = bytes(raw).split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
    return text[:120] or "<set>"


def _copy(src: str, dst: str) -> bool:
    import shutil

    try:
        shutil.copyfile(src, dst)
        return True
    except OSError:
        return False
