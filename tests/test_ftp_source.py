from __future__ import annotations

import pikepdf
import pytest

from metacls.config import DEFAULT_FILETYPES
from metacls.ftp_source import FtpFetchError, fetch_ftp, upload_ftp


def _dirty_pdf(path, author="FTP Author"):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(100, 100))
    pdf.docinfo["/Author"] = author
    pdf.save(str(path))


@pytest.fixture
def ftp_tree(ftp_server):
    root = ftp_server["root"]
    (root / "sub").mkdir()
    _dirty_pdf(root / "leak.pdf", "Top Level")
    (root / "notes.txt").write_text("not a supported type")
    _dirty_pdf(root / "sub" / "nested.pdf", "Nested Author")
    return ftp_server


def test_fetch_recursive_finds_nested_file(ftp_tree, tmp_path):
    dest = tmp_path / "down"
    dest.mkdir()
    res = fetch_ftp(host="127.0.0.1", port=ftp_tree["port"], username="tester",
                    password="s3cret", remote_dir="/", dest_dir=str(dest),
                    extensions=set(DEFAULT_FILETYPES), recursive=True)
    got = {f.remote_path for f in res.files}
    assert got == {"leak.pdf", "sub/nested.pdf"}
    assert res.skipped_other_types == 1  # notes.txt
    assert (dest / "leak.pdf").is_file()
    assert (dest / "sub" / "nested.pdf").is_file()


def test_fetch_non_recursive_skips_subdirectory(ftp_tree, tmp_path):
    dest = tmp_path / "down"
    dest.mkdir()
    res = fetch_ftp(host="127.0.0.1", port=ftp_tree["port"], username="tester",
                    password="s3cret", remote_dir="/", dest_dir=str(dest),
                    extensions=set(DEFAULT_FILETYPES), recursive=False)
    assert {f.remote_path for f in res.files} == {"leak.pdf"}


def test_fetch_anonymous_login(ftp_tree, tmp_path):
    dest = tmp_path / "down"
    dest.mkdir()
    res = fetch_ftp(host="127.0.0.1", port=ftp_tree["port"], remote_dir="/",
                    dest_dir=str(dest), extensions=set(DEFAULT_FILETYPES), recursive=False)
    assert {f.remote_path for f in res.files} == {"leak.pdf"}


def test_fetch_wrong_password_raises(ftp_tree, tmp_path):
    with pytest.raises(FtpFetchError, match="could not connect"):
        fetch_ftp(host="127.0.0.1", port=ftp_tree["port"], username="tester",
                  password="WRONG", remote_dir="/", dest_dir=str(tmp_path / "d"),
                  extensions=set(DEFAULT_FILETYPES))


def test_fetch_no_matching_extension_raises(ftp_tree, tmp_path):
    with pytest.raises(FtpFetchError, match="no matching files"):
        fetch_ftp(host="127.0.0.1", port=ftp_tree["port"], username="tester",
                  password="s3cret", remote_dir="/", dest_dir=str(tmp_path / "d"),
                  extensions={"docx"})


def test_fetch_bad_host_raises():
    with pytest.raises(FtpFetchError, match="could not connect"):
        fetch_ftp(host="127.0.0.1", port=39999, dest_dir="/tmp", extensions={"pdf"}, timeout=2)


def test_fetch_empty_host_raises():
    with pytest.raises(FtpFetchError, match="host is required"):
        fetch_ftp(host="", dest_dir="/tmp", extensions={"pdf"})


def test_max_files_truncates(ftp_tree, tmp_path):
    dest = tmp_path / "down"
    dest.mkdir()
    res = fetch_ftp(host="127.0.0.1", port=ftp_tree["port"], username="tester",
                    password="s3cret", remote_dir="/", dest_dir=str(dest),
                    extensions=set(DEFAULT_FILETYPES), recursive=True, max_files=1)
    assert len(res.files) == 1
    assert res.truncated is True


def test_upload_writes_back_and_overwrites(ftp_tree, tmp_path):
    # "clean" a local copy by just rewriting it, then push it back.
    local = tmp_path / "cleaned.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(50, 50))
    pdf.save(str(local))  # no /Author this time

    with pikepdf.open(str(ftp_tree["root"] / "leak.pdf")) as pdf_before:
        assert "/Author" in pdf_before.docinfo

    n = upload_ftp(host="127.0.0.1", port=ftp_tree["port"], username="tester",
                   password="s3cret", remote_dir="/", files=[("leak.pdf", str(local))])
    assert n == 1
    with pikepdf.open(str(ftp_tree["root"] / "leak.pdf")) as pdf_after:
        assert "/Author" not in pdf_after.docinfo


def test_upload_to_subdirectory_creates_it(ftp_tree, tmp_path):
    local = tmp_path / "cleaned.pdf"
    _dirty_pdf(local, "Whatever")
    n = upload_ftp(host="127.0.0.1", port=ftp_tree["port"], username="tester",
                   password="s3cret", remote_dir="/", files=[("newdir/out.pdf", str(local))])
    assert n == 1
    assert (ftp_tree["root"] / "newdir" / "out.pdf").is_file()
