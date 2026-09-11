"""Scrubbing the same file twice with the same options must produce
byte-identical output — so a scrub is reproducible and auditable.
`--strip-pdf-id` is the one documented exception (it's random on purpose).
"""
from __future__ import annotations

import shutil

import pytest

# reuse the corpus builders (tests/ is on sys.path under pytest)
from test_corpus import _CASES, _HAS_EXIFTOOL, _pdf

from metacls.cleaner import clean_paths
from metacls.config import CleanConfig
from metacls.engines import engine_for


@pytest.mark.parametrize("ext", [e for e in sorted(_CASES) if e != "doc"])
def test_output_is_byte_identical_across_runs(ext, tmp_path):
    if ext == "jpg" and not _HAS_EXIFTOOL:
        pytest.skip("exiftool not installed")

    src = tmp_path / f"c.{ext}"
    _CASES[ext](src, tmp_path)
    assert engine_for(ext) is not None

    a, b = tmp_path / "a", tmp_path / "b"
    r1 = clean_paths([str(src)], CleanConfig(output_dir=str(a)))
    # copy the source fresh (some engines are in-place-ish on temp files)
    src2 = tmp_path / f"c2.{ext}"
    shutil.copy(src, src2)
    r2 = clean_paths([str(src2)], CleanConfig(output_dir=str(b)))

    assert r1.results[0].status == "cleaned" and r2.results[0].status == "cleaned"
    out1 = r1.results[0].out_path
    out2 = r2.results[0].out_path
    with open(out1, "rb") as f1, open(out2, "rb") as f2:
        assert f1.read() == f2.read(), f"{ext}: two scrubs produced different bytes"


def test_strip_pdf_id_is_intentionally_nondeterministic(tmp_path):
    src = tmp_path / "x.pdf"
    _pdf(src)
    cfg = CleanConfig(output_dir=str(tmp_path / "o"), strip_pdf_id=True)
    r1 = clean_paths([str(src)], cfg)
    src2 = tmp_path / "x2.pdf"
    shutil.copy(src, src2)
    r2 = clean_paths([str(src2)], CleanConfig(output_dir=str(tmp_path / "o2"), strip_pdf_id=True))

    b1 = open(r1.results[0].out_path, "rb").read()
    b2 = open(r2.results[0].out_path, "rb").read()
    assert b1 != b2   # the random /ID differs
