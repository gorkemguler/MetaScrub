from __future__ import annotations

import os

import pytest

from metascrub.config import DEFAULT_FILETYPES
from metascrub.scanner import iter_files


def test_walks_recursively_and_filters_by_extension(dirty_tree):
    files = iter_files([str(dirty_tree)], DEFAULT_FILETYPES)
    names = sorted(os.path.basename(f) for f in files)
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


def test_exclude_glob_skips_files_and_prunes_dirs(dirty_tree):
    by_name = iter_files([str(dirty_tree)], DEFAULT_FILETYPES, exclude=["*.jpg"])
    assert not any(f.endswith(".jpg") for f in by_name)
    assert any(f.endswith("forecast.pdf") for f in by_name)

    pruned = iter_files([str(dirty_tree)], DEFAULT_FILETYPES, exclude=["sub"])
    assert not any("memo2.docx" in f for f in pruned)   # whole subdir gone
    assert any("memo.docx" in f for f in pruned)         # top-level kept


def test_exclude_matches_relative_path(dirty_tree):
    files = iter_files([str(dirty_tree)], DEFAULT_FILETYPES, exclude=["sub/*"])
    assert not any("memo2.docx" in f for f in files)


def test_no_follow_symlinks_skips_linked_file(dirty_tree, tmp_path):
    external = tmp_path / "outside.pdf"          # not otherwise in the scan tree
    external.write_bytes((dirty_tree / "forecast.pdf").read_bytes())
    link = dirty_tree / "link.pdf"
    try:
        os.symlink(external, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")

    with_links = iter_files([str(dirty_tree)], DEFAULT_FILETYPES, follow_symlinks=True)
    assert any(f.endswith("link.pdf") for f in with_links)

    without = iter_files([str(dirty_tree)], DEFAULT_FILETYPES, follow_symlinks=False)
    assert not any(f.endswith("link.pdf") for f in without)
