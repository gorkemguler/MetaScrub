from __future__ import annotations

import io
import zipfile

import pytest

from metascrub.web import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(output_dir=str(tmp_path / "out"))
    app.config["TESTING"] = True
    return app.test_client()


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"MetaScrub" in r.data


def test_clean_upload_flow(client, dirty_pdf, dirty_docx):
    data = {
        "lang": "en",
        "keep_icc": "on",
        "files": [
            (io.BytesIO(dirty_pdf.read_bytes()), "forecast.pdf"),
            (io.BytesIO(dirty_docx.read_bytes()), "memo.docx"),
        ],
    }
    r = client.post("/clean", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"removed" in r.data
    assert b"forecast.pdf" in r.data

    # a run dir with reports now exists and shows in history
    h = client.get("/history")
    assert b"web-" in h.data


def test_clean_rejects_empty(client):
    r = client.post("/clean", data={"lang": "en"}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_zip_download_contains_cleaned_file(client, dirty_pdf):
    data = {"lang": "en", "files": [(io.BytesIO(dirty_pdf.read_bytes()), "f.pdf")]}
    client.post("/clean", data=data, content_type="multipart/form-data")
    run_id = _latest_run(client)
    z = client.get(f"/zip/{run_id}")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.data)).namelist()
    assert "cleaned/f.pdf" in names
    assert "report.json" in names


def test_path_traversal_blocked(client):
    assert client.get("/report/..%2f..%2fetc").status_code == 404
    assert client.get("/file/nope/x.pdf").status_code == 404


def test_report_reachable_when_output_dir_is_under_a_symlink(tmp_path, dirty_pdf):
    # A run dir under a symlinked output_dir (like /tmp -> /private/tmp on
    # macOS) must still resolve — the traversal guard compares realpaths.
    real = tmp_path / "real_out"
    real.mkdir()
    link = tmp_path / "linked_out"
    link.symlink_to(real)

    app = create_app(output_dir=str(link))
    app.config["TESTING"] = True
    c = app.test_client()

    c.post("/clean", data={"lang": "en", "files": [(io.BytesIO(dirty_pdf.read_bytes()), "f.pdf")]},
           content_type="multipart/form-data")
    run_id = next(p.name for p in real.iterdir() if p.name.startswith("web-"))
    assert c.get(f"/report/{run_id}").status_code == 200
    assert c.get(f"/zip/{run_id}").status_code == 200


def _latest_run(client) -> str:
    h = client.get("/history").data.decode()
    start = h.index("web-")
    return h[start:h.index("<", start)]
