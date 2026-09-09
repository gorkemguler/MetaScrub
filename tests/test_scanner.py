from __future__ import annotations

from metascrub.config import DEFAULT_FILETYPES
from metascrub.scanner import iter_files


def test_walks_recursively_and_filters_by_extension(dirty_tree):
    files = iter_files([str(dirty_tree)], DEFAULT_FILETYPES)
    names = sorted(f.rsplit("/", 1)[-1] for f in files)
    assert names == ["forecast.pdf", "memo.docx", "memo2.docx", "photo.jpg"]


def test_no_recursive_skips_subdirs(dirty_tree):
    files = iter_files([str(dirty_tree)], DEFAULT_FILETYPES, recursive=False)
    assert not any("memo2.docx" in f for f in files)


def test_explicit_file_included_regardless_of_filter(dirty_tree):
    txt = str(dirty_tree / "notes.txt")
    assert iter_files([txt], ["pdf"]) == [txt]


def test_dedupes_overlapping_roots(dirty_tree):
    one = str(dirty_tree / "forecast.pdf")
    files = iter_files([str(dirty_tree), one], DEFAULT_FILETYPES)
    assert files.count(one) <= 1
    assert sum(1 for f in files if f.endswith("forecast.pdf")) == 1
