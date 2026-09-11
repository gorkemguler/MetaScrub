from __future__ import annotations

import shutil
import struct
import subprocess

import pytest

from metacls.config import CleanConfig
from metacls.engines.ebml_riff import (
    probe_avi,
    probe_matroska,
    scrub_avi,
    scrub_matroska,
)
from metacls.engines.media import MediaEngine

_HAS_FFMPEG = shutil.which("ffmpeg") is not None

# --- tiny hand-built containers (structure only — not meant to play) --------


def _vint(n: int) -> bytes:
    for length in range(1, 9):
        if n < (1 << (7 * length)) - 1:
            return (n | (1 << (7 * length))).to_bytes(length, "big")
    raise ValueError(n)


def _el(elem_id: bytes, payload: bytes) -> bytes:
    return elem_id + _vint(len(payload)) + payload


def _mkv_bytes() -> bytes:
    header = _el(b"\x1a\x45\xdf\xa3", _el(b"\x42\x82", b"matroska"))  # EBML > DocType
    info = _el(
        b"\x15\x49\xa9\x66",
        _el(b"\x7b\xa9", b"Secret Movie Title")                       # Title
        + _el(b"\x4d\x80", b"libmakescrub 1.0")                       # MuxingApp
        + _el(b"\x57\x41", b"mkvmerge v80.0")                         # WritingApp
        + _el(b"\x44\x61", struct.pack(">q", 123456789)),            # DateUTC
    )
    simple_tag = _el(
        b"\x67\xc8",
        _el(b"\x45\xa3", b"ARTIST") + _el(b"\x44\x87", b"Jane Director"),
    )
    tags = _el(b"\x12\x54\xc3\x67", _el(b"\x73\x73", simple_tag))
    segment = _el(b"\x18\x53\x80\x67", info + tags)
    return header + segment


def _avi_bytes() -> bytes:
    def chunk(fourcc: bytes, data: bytes) -> bytes:
        out = fourcc + struct.pack("<I", len(data)) + data
        return out + b"\x00" * (len(data) & 1)

    info = b"INFO" + chunk(b"INAM", b"Secret AVI Name\x00") + chunk(b"ISFT", b"AviMuxScrub 9\x00")
    info_list = b"LIST" + struct.pack("<I", len(info)) + info
    idit = chunk(b"IDIT", b"Mon Jan 01 00:00:00 2024\x00")
    body = b"AVI " + info_list + idit
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --- Matroska / WebM -------------------------------------------------------------


def test_matroska_probe_sees_tags_and_info(tmp_path):
    f = tmp_path / "clip.mkv"
    f.write_bytes(_mkv_bytes())
    fields = {name for name, _ in probe_matroska(str(f))}
    assert "Tags" in fields
    assert {"Info Title", "Info MuxingApp", "Info WritingApp", "Info DateUTC"} <= fields


def test_matroska_scrub_blanks_metadata_same_length(tmp_path):
    src = tmp_path / "clip.mkv"
    src.write_bytes(_mkv_bytes())
    dst = tmp_path / "clean.mkv"

    ok, removed = scrub_matroska(str(src), str(dst))
    assert ok and removed
    out = dst.read_bytes()
    assert len(out) == src.stat().st_size                 # in-place-safe: identical length
    for needle in (b"Secret Movie Title", b"Jane Director", b"mkvmerge", b"libmakescrub", b"ARTIST"):
        assert needle not in out
    assert b"\x1a\x45\xdf\xa3" == out[:4]                 # still starts with the EBML header
    assert probe_matroska(str(dst)) == []


def test_matroska_via_media_engine(tmp_path):
    src = tmp_path / "clip.mkv"
    src.write_bytes(_mkv_bytes())
    dst = tmp_path / "out.mkv"

    before = MediaEngine().probe(str(src))
    assert before
    result = MediaEngine().strip(str(src), str(dst), CleanConfig())
    assert result.status == "cleaned"
    assert MediaEngine().probe(str(dst)) == []


def test_matroska_source_not_modified(tmp_path):
    src = tmp_path / "clip.mkv"
    original = _mkv_bytes()
    src.write_bytes(original)
    scrub_matroska(str(src), str(tmp_path / "o.mkv"))
    assert src.read_bytes() == original


# --- AVI ----------------------------------------------------------------------


def test_avi_probe_and_scrub(tmp_path):
    src = tmp_path / "clip.avi"
    src.write_bytes(_avi_bytes())
    fields = {name for name, _ in probe_avi(str(src))}
    assert {"Title", "Software", "IDIT"} <= fields

    dst = tmp_path / "clean.avi"
    ok, removed = scrub_avi(str(src), str(dst))
    assert ok and removed
    out = dst.read_bytes()
    assert len(out) == src.stat().st_size
    for needle in (b"Secret AVI Name", b"AviMuxScrub", b"Jan 01 00:00:00 2024"):
        assert needle not in out
    assert out[:4] == b"RIFF" and out[8:12] == b"AVI "
    assert b"JUNK" in out                                 # relabelled, not removed
    assert probe_avi(str(dst)) == []


def test_avi_via_media_engine_in_place(tmp_path):
    src = tmp_path / "clip.avi"
    src.write_bytes(_avi_bytes())
    dst = tmp_path / "out.avi"
    result = MediaEngine().strip(str(src), str(dst), CleanConfig())
    assert result.status == "cleaned"
    assert MediaEngine().probe(str(dst)) == []


# --- real containers, when ffmpeg is available (CI) --------------------------


def _ffmpeg_make(path, extra):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=32x32:rate=1:duration=1",
         *extra, str(path)],
        check=True, capture_output=True, timeout=60,
    )


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
def test_real_mkv_roundtrips_and_stays_valid(tmp_path):
    src = tmp_path / "real.mkv"
    _ffmpeg_make(src, ["-metadata", "title=Secret Title", "-metadata", "ARTIST=Jane Director"])
    assert MediaEngine().probe(str(src))

    dst = tmp_path / "clean.mkv"
    result = MediaEngine().strip(str(src), str(dst), CleanConfig())
    assert result.status == "cleaned"
    assert dst.stat().st_size == src.stat().st_size
    assert b"Secret Title" not in dst.read_bytes() and b"Jane Director" not in dst.read_bytes()
    # ffmpeg can still demux the scrubbed file
    probe = subprocess.run(["ffmpeg", "-v", "error", "-i", str(dst), "-f", "null", "-"],
                           capture_output=True, timeout=60)
    assert probe.returncode == 0, probe.stderr.decode()


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
def test_real_avi_roundtrips_and_stays_valid(tmp_path):
    src = tmp_path / "real.avi"
    _ffmpeg_make(src, ["-metadata", "title=Secret Title", "-metadata", "ISFT=SecretMuxer"])
    dst = tmp_path / "clean.avi"
    result = MediaEngine().strip(str(src), str(dst), CleanConfig())
    assert result.status == "cleaned"
    assert dst.stat().st_size == src.stat().st_size
    probe = subprocess.run(["ffmpeg", "-v", "error", "-i", str(dst), "-f", "null", "-"],
                           capture_output=True, timeout=60)
    assert probe.returncode == 0, probe.stderr.decode()
