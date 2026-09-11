from __future__ import annotations

import shutil
import subprocess

import pytest

from metacls.config import CleanConfig
from metacls.engines.exiftool import read_tags
from metacls.engines.image import ImageEngine

needs_exiftool = pytest.mark.skipif(
    shutil.which("exiftool") is None, reason="exiftool binary not installed"
)


@needs_exiftool
def test_probe_lists_exif_and_gps(dirty_jpg):
    rows = ImageEngine().probe(str(dirty_jpg))
    fields = {r.field for r in rows}
    assert "Artist" in fields
    assert "Model" in fields
    assert any(r.field.startswith("GPS") for r in rows)


@needs_exiftool
def test_strip_removes_exif_gps_keeps_pixels(dirty_jpg, tmp_path):
    dst = tmp_path / "clean.jpg"
    result = ImageEngine().strip(str(dirty_jpg), str(dst), CleanConfig())

    assert result.status == "cleaned"
    assert result.removed
    assert dst.exists()

    remaining = read_tags(str(dst))
    assert not any(k.split(":")[-1] in ("Artist", "Make", "Model", "Software", "Copyright") for k in remaining)
    assert not any("GPS" in k for k in remaining)
    assert ImageEngine().probe(str(dst)) == []


@needs_exiftool
def test_source_not_modified(dirty_jpg, tmp_path):
    before = dirty_jpg.read_bytes()
    ImageEngine().strip(str(dirty_jpg), str(tmp_path / "c.jpg"), CleanConfig())
    assert dirty_jpg.read_bytes() == before


# canonical 43-byte 1x1 GIF89a (see tests/test_corpus.py for the layout)
_GIF_1PX = bytes.fromhex(
    "474946383961" "0100" "0100" "80" "00" "00" "000000" "ffffff"
    "21f9" "04" "01" "0000" "00" "00" "2c" "0000" "0000" "0100" "0100" "00"
    "02" "02" "4401" "00" "3b"
)


@needs_exiftool
def test_gif_comment_and_xmp_stripped(tmp_path):
    src = tmp_path / "banner.gif"
    src.write_bytes(_GIF_1PX)
    subprocess.run(
        ["exiftool", "-overwrite_original", "-Comment=Made by Secret Sam",
         "-XMP:Creator=Secret Sam", str(src)],
        check=True, capture_output=True,
    )

    fields = {r.field for r in ImageEngine().probe(str(src))}
    assert "Comment" in fields and "Creator" in fields

    dst = tmp_path / "clean.gif"
    result = ImageEngine().strip(str(src), str(dst), CleanConfig())
    assert result.status == "cleaned"

    remaining = read_tags(str(dst))
    assert remaining == {}, remaining
    assert ImageEngine().probe(str(dst)) == []
    # the GIF is still a valid 1x1 image, not truncated
    assert dst.read_bytes().startswith(b"GIF89a") and dst.read_bytes().endswith(b";")
