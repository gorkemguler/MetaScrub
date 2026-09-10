"""A tiny, *in-place* scrubber for OLE2 (Compound File Binary) property
streams — `\\x05SummaryInformation` and `\\x05DocumentSummaryInformation`.

It never changes any stream's size or the file's structure: it locates the
bytes of each string / FILETIME property value and overwrites them with
zeros where they leak identity (author, last-saved-by, company, manager,
template, title, timestamps, custom properties). That keeps the FAT, the
mini-FAT and the directory untouched, so the risk of corrupting an
unrelated stream is nil — the trade-off is that it only reaches what lives
in those two property sets (which is exactly what `metascrub inspect`
reads for a legacy file, and what Explorer / Office show under
"Properties").
"""
from __future__ import annotations

import struct

import olefile

_ENDOFCHAIN = 0xFFFFFFFE
_FREESECT = 0xFFFFFFFF

# Mixed-endian GUID bytes for the three well-known property-set FMTIDs.
_FMTID_SUMMARY = bytes.fromhex("e0859ff2f94f6810ab9108002b27b3d9")
_FMTID_DOCSUMMARY = bytes.fromhex("02d5cdd59c2e1b10939708002b2cf9ae")
_FMTID_USERDEFINED = bytes.fromhex("05d5cdd59c2e1b10939708002b2cf9ae")

# SummaryInformation property IDs worth blanking (string + FILETIME).
_SUMMARY_IDS = {2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 18}
# DocumentSummaryInformation: manager (14), company (15).
_DOCSUMMARY_IDS = {14, 15}

_VT_LPSTR = 0x1E
_VT_LPWSTR = 0x1F
_VT_FILETIME = 0x40


def scrub_ole2(src: str, dst: str) -> tuple[bool, list[tuple[str, str]]]:
    """Write a scrubbed copy of `src` to `dst`. Returns (changed, removed)
    where `removed` is a list of (namespace, field) that were blanked.
    (changed=False, []) means nothing was found to blank — the caller can
    just copy the file. Raises on a malformed container.
    """
    with open(src, "rb") as fh:
        data = bytearray(fh.read())

    ole = olefile.OleFileIO(src)
    try:
        ole.loadminifat()
        removed: list[tuple[str, str]] = []
        for stream_name, ns in (
            ("\x05SummaryInformation", "SummaryInformation"),
            ("\x05DocumentSummaryInformation", "DocumentSummaryInformation"),
        ):
            if not ole.exists(stream_name):
                continue
            entry = _entry(ole, stream_name)
            runs = _stream_runs(ole, entry)
            buf = bytearray(_gather(data, runs, entry.size))
            hits = _blank_property_set(buf)
            if hits:
                _scatter(data, runs, buf)
                removed += [(ns, f) for f in hits]
    finally:
        ole.close()

    with open(dst, "wb") as fh:
        fh.write(data)
    return bool(removed), removed


# --- CFB sector arithmetic ------------------------------------------------


def _entry(ole: olefile.OleFileIO, name: str):
    for e in ole.direntries:
        if e is not None and e.name == name:
            return e
    raise KeyError(name)


def _big_chain(fat, start: int) -> list[int]:
    out: list[int] = []
    s = start
    while s not in (_ENDOFCHAIN, _FREESECT) and 0 <= s < len(fat):
        out.append(s)
        s = fat[s]
        if len(out) > len(fat):  # cycle guard
            break
    return out


def _stream_runs(ole: olefile.OleFileIO, entry) -> list[tuple[int, int]]:
    """(file_offset, length) runs covering the stream's bytes in order."""
    ss = ole.sectorsize
    if entry.size >= ole.minisectorcutoff:
        return [((s + 1) * ss, ss) for s in _big_chain(ole.fat, entry.isectStart)]

    mini_big = _big_chain(ole.fat, ole.root.isectStart)
    mss = ole.minisectorsize

    def mini_pos_offset(pos: int) -> int:
        bs = mini_big[pos // ss]
        return (bs + 1) * ss + (pos % ss)

    runs: list[tuple[int, int]] = []
    m = entry.isectStart
    guard = 0
    while m not in (_ENDOFCHAIN, _FREESECT) and 0 <= m < len(ole.minifat):
        runs.append((mini_pos_offset(m * mss), mss))
        m = ole.minifat[m]
        guard += 1
        if guard > len(ole.minifat):
            break
    return runs


def _gather(data: bytes | bytearray, runs: list[tuple[int, int]], size: int) -> bytes:
    out = bytearray()
    for off, length in runs:
        out += data[off:off + length]
        if len(out) >= size:
            break
    return bytes(out[:size])


def _scatter(data: bytearray, runs: list[tuple[int, int]], buf: bytes | bytearray) -> None:
    pos = 0
    for off, length in runs:
        take = min(length, len(buf) - pos)
        if take <= 0:
            break
        data[off:off + take] = buf[pos:pos + take]
        pos += take


# --- property-set-stream parsing ---------------------------------------------


def _blank_property_set(buf: bytearray) -> list[str]:
    if len(buf) < 28 or buf[0:2] != b"\xfe\xff":
        return []
    n_sections = struct.unpack_from("<I", buf, 24)[0]
    blanked: list[str] = []
    p = 28
    for _ in range(n_sections):
        if p + 20 > len(buf):
            break
        fmtid = bytes(buf[p:p + 16])
        section_off = struct.unpack_from("<I", buf, p + 16)[0]
        p += 20
        if fmtid == _FMTID_SUMMARY:
            wanted, blank_all_strings = _SUMMARY_IDS, False
        elif fmtid == _FMTID_DOCSUMMARY:
            wanted, blank_all_strings = _DOCSUMMARY_IDS, False
        elif fmtid == _FMTID_USERDEFINED:
            wanted, blank_all_strings = set(), True
        else:
            continue
        blanked += _blank_section(buf, section_off, wanted, blank_all_strings)
    return blanked


def _blank_section(buf: bytearray, sec_off: int, wanted: set[int], blank_all_strings: bool) -> list[str]:
    if sec_off + 8 > len(buf):
        return []
    count = struct.unpack_from("<I", buf, sec_off + 4)[0]
    out: list[str] = []
    entry_p = sec_off + 8
    for _ in range(count):
        if entry_p + 8 > len(buf):
            break
        propid, prop_off = struct.unpack_from("<II", buf, entry_p)
        entry_p += 8
        vpos = sec_off + prop_off
        if vpos + 4 > len(buf):
            continue
        vtype = struct.unpack_from("<I", buf, vpos)[0]
        take_string = blank_all_strings or propid in wanted
        if vtype in (_VT_LPSTR, _VT_LPWSTR) and (take_string or propid in wanted):
            cch = struct.unpack_from("<I", buf, vpos + 4)[0]
            nbytes = cch * (2 if vtype == _VT_LPWSTR else 1)
            start = vpos + 8
            if 0 < nbytes <= len(buf) - start:
                if any(buf[start:start + nbytes]):
                    for i in range(start, start + nbytes):
                        buf[i] = 0
                    out.append(f"property {propid}")
        elif vtype == _VT_FILETIME and propid in wanted:
            start = vpos + 4
            if start + 8 <= len(buf) and any(buf[start:start + 8]):
                for i in range(start, start + 8):
                    buf[i] = 0
                out.append(f"property {propid}")
    return out
