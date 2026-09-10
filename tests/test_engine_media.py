from __future__ import annotations

import pytest

pytest.importorskip("mutagen")

import mutagen  # noqa: E402
from mutagen.easyid3 import EasyID3  # noqa: E402

from metascrub.config import CleanConfig  # noqa: E402
from metascrub.engines import engine_for  # noqa: E402
from metascrub.engines.media import MediaEngine  # noqa: E402

# MPEG-1 Layer III, 128 kbps, 44100 Hz, mono -> 417-byte frames.
_FRAME = bytes.fromhex("fffb9040") + b"\x00" * (417 - 4)


@pytest.fixture
def dirty_mp3(tmp_path):
    p = tmp_path / "song.mp3"
    p.write_bytes(_FRAME * 40)
    t = EasyID3()
    t["artist"] = "Track Tina"
    t["album"] = "Secret Sessions"
    t["title"] = "Demo"
    t.save(str(p))
    return p


def test_media_dispatch():
    for ext in ("mp3", "m4a", "flac", "mp4", "mov", "mkv"):
        assert isinstance(engine_for(ext), MediaEngine)


def test_probe_lists_audio_tags(dirty_mp3):
    fields = {r.field for r in MediaEngine().probe(str(dirty_mp3))}
    assert {"TPE1", "TALB", "TIT2"} <= fields


def test_strip_removes_all_audio_tags(dirty_mp3, tmp_path):
    dst = tmp_path / "clean.mp3"
    result = MediaEngine().strip(str(dirty_mp3), str(dst), CleanConfig())

    assert result.status == "cleaned"
    assert len(result.removed) == 3
    assert mutagen.File(str(dst)).tags in (None, {})
    assert MediaEngine().probe(str(dst)) == []

    # audio frames survive (same tail bytes as the source's audio)
    assert dst.read_bytes().endswith(_FRAME)


def test_source_not_modified(dirty_mp3, tmp_path):
    before = dirty_mp3.read_bytes()
    MediaEngine().strip(str(dirty_mp3), str(tmp_path / "c.mp3"), CleanConfig())
    assert dirty_mp3.read_bytes() == before
