"""Golden corpus: a spread of deliberately dirty files, one per format /
engine path. For every one: probe() must find metadata, clean() must
remove it, and a re-probe of the *output* must come back empty.

Files are generated (not checked-in binaries) so the corpus stays
deterministic and reviewable.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import zipfile

import pikepdf
import pytest

# a real 1x1 baseline JPEG (same carrier the conftest image fixtures use)
_JPEG_1PX = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
    "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
    "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
    "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iii"
    "gD//2Q=="
)

# a canonical 43-byte 1x1 GIF89a (built from spec so the corpus stays
# reviewable — no checked-in binary)
_GIF_1PX = bytes.fromhex(
    "474946383961"            # "GIF89a"
    "0100" "0100"             # width = 1, height = 1
    "80" "00" "00"            # packed (global colour table, 2 colours), bg, aspect
    "000000" "ffffff"         # colour table: black, white
    "21f9" "04" "01" "0000" "00" "00"       # graphic control extension
    "2c" "0000" "0000" "0100" "0100" "00"   # image descriptor
    "02" "02" "4401" "00"     # LZW min code size, sub-block, data, terminator
    "3b"                      # trailer
)

from metascrub.cleaner import clean_paths
from metascrub.config import CleanConfig
from metascrub.engines import engine_for

_HAS_EXIFTOOL = shutil.which("exiftool") is not None

_DIRTY_CORE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"'
    ' xmlns:dc="http://purl.org/dc/elements/1.1/">'
    "<dc:creator>Corpus Creator</dc:creator><cp:lastModifiedBy>Corpus Editor</cp:lastModifiedBy>"
    "<dc:title>Corpus Secret Title</dc:title></cp:coreProperties>"
)


def _ooxml(path, main_part, main_ct):
    ct = (f'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          f'<Default Extension="xml" ContentType="application/xml"/>'
          f'<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
          f'<Override PartName="/{main_part}" ContentType="{main_ct}"/></Types>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{main_part}"/>'
            '<Relationship Id="r2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("docProps/core.xml", _DIRTY_CORE)
        z.writestr(main_part, "<root/>")


def _odf(path, mimetype):
    meta = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"><office:meta>'
        "<meta:initial-creator>Corpus Person</meta:initial-creator>"
        "<meta:generator>CorpusOffice/9</meta:generator></office:meta></office:document-meta>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", mimetype, compress_type=zipfile.ZIP_STORED)
        z.writestr("content.xml", '<?xml version="1.0"?><doc/>')
        z.writestr("meta.xml", meta)


def _pdf(path):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.docinfo["/Author"] = "Corpus Author"
    pdf.docinfo["/Producer"] = "Corpus Writer 1.0"
    with pdf.open_metadata() as m:
        m["dc:creator"] = ["Corpus Author"]
    pdf.save(str(path))


def _svg(path):
    path.write_text(
        '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"'
        ' width="10" height="10" inkscape:version="1.1">'
        "<metadata><dc:creator>Corpus Artist</dc:creator></metadata>"
        '<rect width="10" height="10"/></svg>'
    )


def _image(path):
    path.write_bytes(_JPEG_1PX)
    subprocess.run(["exiftool", "-q", "-overwrite_original", "-Artist=Corpus Shooter",
                    "-Make=CorpusCam", "-GPSLatitude=1.0", "-GPSLatitudeRef=N", str(path)], check=False)


def _gif(path):
    path.write_bytes(_GIF_1PX)
    subprocess.run(["exiftool", "-q", "-overwrite_original", "-Comment=Corpus Commenter",
                    "-XMP:Creator=Corpus Artist", str(path)], check=False)


def _doc(path, tmp_path):
    docx = tmp_path / "_seed.docx"
    _ooxml(docx, "word/document.xml",
           "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    prof = tmp_path / "_lo"
    subprocess.run(["soffice", "--headless", "--norestore", "--nolockcheck",
                    f"-env:UserInstallation=file://{prof}", "--convert-to", "doc",
                    "--outdir", str(tmp_path), str(docx)], capture_output=True, timeout=120, check=False)
    made = tmp_path / "_seed.doc"
    if not made.is_file():
        pytest.skip("LibreOffice did not produce a .doc")
    shutil.move(str(made), str(path))


_CASES = {
    "pdf": lambda p, t: _pdf(p),
    "docx": lambda p, t: _ooxml(p, "word/document.xml", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"),
    "xlsx": lambda p, t: _ooxml(p, "xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"),
    "pptx": lambda p, t: _ooxml(p, "ppt/presentation.xml", "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"),
    "odt": lambda p, t: _odf(p, "application/vnd.oasis.opendocument.text"),
    "ods": lambda p, t: _odf(p, "application/vnd.oasis.opendocument.spreadsheet"),
    "svg": lambda p, t: _svg(p),
    "jpg": lambda p, t: _image(p),
    "gif": lambda p, t: _gif(p),
    "doc": _doc,
}

# Formats whose fixture needs exiftool to carry any metadata at all.
_NEEDS_EXIFTOOL = {"jpg", "gif"}


@pytest.mark.parametrize("ext", [
    pytest.param(e, marks=pytest.mark.slow) if e == "doc" else e for e in sorted(_CASES)
])
def test_corpus_file_scrubs_to_zero_residual(ext, tmp_path):
    if ext in _NEEDS_EXIFTOOL and not _HAS_EXIFTOOL:
        pytest.skip("exiftool not installed")
    if ext == "doc" and shutil.which("soffice") is None and shutil.which("libreoffice") is None:
        pytest.skip("LibreOffice not installed")

    src = tmp_path / f"corpus.{ext}"
    _CASES[ext](src, tmp_path)

    engine = engine_for(ext)
    assert engine is not None
    assert engine.probe(str(src)), f"{ext}: fixture carried no metadata to begin with"

    out = tmp_path / "out"
    report = clean_paths([str(src)], CleanConfig(output_dir=str(out)))
    assert len(report.results) == 1
    r = report.results[0]
    assert r.status == "cleaned", f"{ext}: {r.reason or r.error}"
    assert not r.residual, f"{ext}: residual {r.residual}"

    verify_engine = engine_for(r.out_path.rsplit(".", 1)[-1]) or engine
    assert verify_engine.probe(r.out_path) == [], f"{ext}: re-probe found metadata"
