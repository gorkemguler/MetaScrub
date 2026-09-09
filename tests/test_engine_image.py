from __future__ import annotations

import shutil

import pytest

from metascrub.config import CleanConfig
from metascrub.engines.image import ImageEngine
from metascrub.engines.exiftool import read_tags

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
