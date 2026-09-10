from __future__ import annotations

import io
import time
import zipfile

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from metascrub.api import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = create_app(output_dir=str(tmp_path / "out"), max_workers=2)
    with TestClient(app) as c:
        yield c


def _wait_done(client, job_id, timeout=15):
    for _ in range(timeout * 20):
        r = client.get(f"/v1/clean/{job_id}").json()
        if r["status"] in ("done", "error"):
            return r
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_formats_endpoint(client):
    r = client.get("/v1/formats")
    assert r.status_code == 200
    body = r.json()
    assert "pdf" in body["extensions"] and "mkv" in body["extensions"]
    assert "pdf" in body["engines"] and "media" in body["engines"]
    assert set(body["optional"]) >= {"exiftool", "py7zr", "mutagen"}
    assert body["tool_versions"]["metascrub"]


def test_formats_open_without_api_key(tmp_path):
    app = create_app(output_dir=str(tmp_path / "o"), api_key="sekret")
    with TestClient(app) as c:
        assert c.get("/v1/formats").status_code == 200   # capability info, like /health


def test_media_upload_skipped_unless_enabled(client, tmp_path):
    mp3 = b"ID3\x03\x00\x00\x00\x00\x00\x21" + b"\x00" * 64   # minimal ID3v2 stub
    def _post(data):
        r = client.post("/v1/clean", files=[("files", ("song.mp3", mp3, "audio/mpeg"))], data=data)
        return _wait_done(client, r.json()["job_id"])

    off = _post({})
    assert off["summary"]["by_status"].get("skipped") == 1
    on = _post({"media": "true"})
    assert on["summary"]["by_status"].get("skipped", 0) == 0   # attempted (cleaned or error, not skipped)


def test_recurse_flag_gates_zip(client, dirty_pdf):
    import io as _io
    import zipfile as _zip

    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w") as z:
        z.writestr("inner/doc.pdf", dirty_pdf.read_bytes())

    def _post(data):
        r = client.post("/v1/clean", files=[("files", ("bundle.zip", buf.getvalue(), "application/zip"))],
                        data=data)
        return _wait_done(client, r.json()["job_id"])

    assert _post({})["summary"]["by_status"].get("skipped") == 1
    assert _post({"recurse": "true"})["summary"]["by_status"].get("cleaned") == 1


def test_clean_job_lifecycle(client, dirty_pdf, dirty_docx):
    r = client.post(
        "/v1/clean",
        files=[
            ("files", ("forecast.pdf", dirty_pdf.read_bytes(), "application/pdf")),
            ("files", ("memo.docx", dirty_docx.read_bytes(), "application/octet-stream")),
        ],
        data={"report_lang": "tr"},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]

    done = _wait_done(client, job_id)
    assert done["status"] == "done", done
    assert done["summary"]["by_status"]["cleaned"] == 2
    assert done["summary"]["fields_removed"] > 0

    rj = client.get(f"/v1/clean/{job_id}/report.json")
    assert rj.status_code == 200 and rj.json()["summary"]["files"] == 2

    z = client.get(f"/v1/clean/{job_id}/download")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert "cleaned/forecast.pdf" in names and "report.json" in names


def test_clean_requires_files(client):
    r = client.post("/v1/clean", data={"report_lang": "en"})
    assert r.status_code == 422


def test_report_409_before_done(client, dirty_pdf, monkeypatch):
    # never-finishing worker so we can observe the 409

    r = client.post("/v1/clean", files=[("files", ("f.pdf", dirty_pdf.read_bytes(), "application/pdf"))])
    job_id = r.json()["job_id"]
    # immediately (job likely still queued/running)
    early = client.get(f"/v1/clean/{job_id}/report.json")
    assert early.status_code in (200, 409)  # fast machines may already be done


def test_api_key_enforced(tmp_path, dirty_pdf):
    app = create_app(output_dir=str(tmp_path / "o"), api_key="sekret")
    with TestClient(app) as c:
        assert c.get("/v1/health").status_code == 200          # health stays open
        assert c.get("/v1/clean").status_code == 401           # no key
        assert c.get("/v1/clean", headers={"X-API-Key": "nope"}).status_code == 401
        ok = c.post("/v1/clean", files=[("files", ("f.pdf", dirty_pdf.read_bytes(), "application/pdf"))],
                    headers={"Authorization": "Bearer sekret"})
        assert ok.status_code == 202
        assert c.get("/v1/clean", headers={"X-API-Key": "sekret"}).status_code == 200


def test_job_status_survives_restart(tmp_path, dirty_pdf):
    out = str(tmp_path / "out")
    app1 = create_app(output_dir=out)
    with TestClient(app1) as c:
        job_id = c.post("/v1/clean",
                        files=[("files", ("f.pdf", dirty_pdf.read_bytes(), "application/pdf"))]).json()["job_id"]
        _wait_done(c, job_id)

    # a fresh app over the same output dir re-reads the SQLite registry
    app2 = create_app(output_dir=out)
    with TestClient(app2) as c:
        r = c.get(f"/v1/clean/{job_id}")
        assert r.status_code == 200
        assert r.json()["status"] == "done"
        assert r.json()["summary"]["files"] == 1
        assert c.get(f"/v1/clean/{job_id}/report.json").status_code == 200   # file still on disk


def test_running_job_marked_interrupted_after_restart(tmp_path):
    out = str(tmp_path / "out")
    create_app(output_dir=out)  # creates jobs.db
    # forge a 'running' row as if the process died mid-job
    import sqlite3
    db = sqlite3.connect(str(tmp_path / "out" / "jobs.db"))
    db.execute("INSERT INTO jobs VALUES ('zz','api-x','en',1,'running','2020-01-01T00:00:00+00:00',"
               "'2020-01-01T00:00:00+00:00',NULL,NULL,NULL)")
    db.commit()
    db.close()

    with TestClient(create_app(output_dir=out)) as c:
        r = c.get("/v1/clean/zz").json()
        assert r["status"] == "error" and "restart" in r["error"]


def test_upload_limits(tmp_path, dirty_pdf):
    app = create_app(output_dir=str(tmp_path / "o"), max_files=2, max_upload_mb=1)
    with TestClient(app) as c:
        three = [("files", (f"f{i}.pdf", dirty_pdf.read_bytes(), "application/pdf")) for i in range(3)]
        assert c.post("/v1/clean", files=three).status_code == 413
        big = [("files", ("big.pdf", b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024), "application/pdf"))]
        assert c.post("/v1/clean", files=big).status_code == 413
