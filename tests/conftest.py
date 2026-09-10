from __future__ import annotations

import base64
import shutil
import subprocess
import zipfile

import pikepdf
import pytest

# A 1x1 baseline JPEG, used as the carrier for EXIF/GPS test data.
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


def exiftool_present() -> bool:
    return shutil.which("exiftool") is not None


needs_exiftool = pytest.mark.skipif(not exiftool_present(), reason="exiftool binary not installed")


@pytest.fixture
def dirty_pdf(tmp_path):
    path = tmp_path / "forecast.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.docinfo["/Author"] = "Alice Example"
    pdf.docinfo["/Title"] = "Q3 Internal Forecast"
    pdf.docinfo["/Producer"] = "Acme PDF Writer 4.2"
    pdf.docinfo["/Creator"] = "Acme Office 2021"
    pdf.docinfo["/CreationDate"] = "D:20240115103000+03'00'"
    with pdf.open_metadata() as m:
        m["dc:creator"] = ["Alice Example"]
        m["dc:title"] = "Q3 Internal Forecast"
    pdf.save(str(path))
    return path


@pytest.fixture
def annotated_pdf(tmp_path):
    path = tmp_path / "reviewed.pdf"
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(300, 300))
    annot = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Text,
        Rect=[10, 10, 30, 30], Contents="Please revise this section",
        T="Reviewer Rachel", M="D:20240501120000Z", CreationDate="D:20240501100000Z",
    ))
    widget = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget,
        Rect=[40, 40, 60, 60], T="signature_field", FT=pikepdf.Name.Tx,
    ))
    page.Annots = pdf.make_indirect(pikepdf.Array([annot, widget]))
    pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(Fields=pikepdf.Array([widget])))
    pdf.save(str(path))
    return path


@pytest.fixture
def attachment_pdf(tmp_path):
    path = tmp_path / "with_attachment.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    ef_stream = pikepdf.Stream(pdf, b"quarterly numbers, do not share")
    ef_stream.Params = pikepdf.Dictionary(
        CreationDate="D:20240101000000Z", ModDate="D:20240102000000Z", Size=30,
    )
    filespec = pdf.make_indirect(pikepdf.Dictionary(
        Type=pikepdf.Name.Filespec, F="q3.xlsx", UF="q3.xlsx",
        Desc="Original at /home/bob/finance/q3.xlsx",
        EF=pikepdf.Dictionary(F=ef_stream),
    ))
    pdf.Root.Names = pdf.make_indirect(pikepdf.Dictionary(
        EmbeddedFiles=pikepdf.Dictionary(Names=pikepdf.Array(["q3.xlsx", filespec])),
    ))
    pdf.save(str(path))
    return path


@pytest.fixture
def form_pdf(tmp_path):
    path = tmp_path / "form.pdf"
    pdf = pikepdf.new()
    page = pdf.add_blank_page(page_size=(300, 200))
    field = pdf.make_indirect(pikepdf.Dictionary(
        FT=pikepdf.Name.Tx, T="applicant_name", V="Jane Q. Public", DV="",
        Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget, Rect=[20, 20, 200, 40],
        AP=pikepdf.Dictionary(N=pikepdf.Stream(pdf, b"BT (Jane Q. Public) Tj ET")),
    ))
    page.Annots = pdf.make_indirect(pikepdf.Array([field]))
    pdf.Root.AcroForm = pdf.make_indirect(
        pikepdf.Dictionary(Fields=pikepdf.Array([field]), NeedAppearances=False)
    )
    pdf.save(str(path))
    return path


@pytest.fixture
def encrypted_pdf(tmp_path):
    path = tmp_path / "locked.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.docinfo["/Author"] = "Alice Example"
    pdf.docinfo["/Title"] = "Sealed Bid"
    pdf.save(str(path), encryption=pikepdf.Encryption(user="s3cret", owner="s3cret"))
    return path


@pytest.fixture
def signed_pdf(tmp_path):
    path = tmp_path / "signed.pdf"
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.docinfo["/Author"] = "Alice Example"
    pdf.Root.AcroForm = pdf.make_indirect(pikepdf.Dictionary(SigFlags=3, Fields=pikepdf.Array()))
    pdf.save(str(path))
    return path


_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/>
</Types>"""
_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/>
</Relationships>"""
_CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:creator>Bob Author</dc:creator>
<cp:lastModifiedBy>Carol Reviewer</cp:lastModifiedBy>
<dc:title>Confidential Merger Memo</dc:title>
<cp:revision>7</cp:revision>
<dcterms:created xsi:type="dcterms:W3CDTF">2024-02-01T09:00:00Z</dcterms:created>
</cp:coreProperties>"""
_APP = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
<Application>Microsoft Office Word</Application>
<Company>Acme Corp</Company>
<Manager>Dave Boss</Manager>
<Template>C:\\Users\\bob\\Templates\\merger.dotx</Template>
</Properties>"""
_CUSTOM = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="Matter Number"><vt:lpwstr>PROJ-2024-0042</vt:lpwstr></property>
</Properties>"""
_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body></w:document>"""
_SETTINGS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:proofState w:spelling="clean"/><w:rsids><w:rsidRoot w:val="00AB12CD"/><w:rsid w:val="00EF3456"/></w:rsids></w:settings>"""


@pytest.fixture
def dirty_docx(tmp_path):
    path = tmp_path / "memo.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("docProps/core.xml", _CORE)
        z.writestr("docProps/app.xml", _APP)
        z.writestr("docProps/custom.xml", _CUSTOM)
        z.writestr("word/document.xml", _DOC)
        z.writestr("word/settings.xml", _SETTINGS)
    return path


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


needs_soffice = pytest.mark.skipif(_soffice() is None, reason="LibreOffice (soffice) not installed")


@pytest.fixture
def legacy_doc(tmp_path, dirty_docx):
    """A real OLE2 .doc, produced by round-tripping the dirty .docx fixture
    through LibreOffice (the author/title survive the conversion)."""
    if _soffice() is None:
        pytest.skip("LibreOffice (soffice) not installed")
    import subprocess

    profile = tmp_path / "loprofile"
    subprocess.run(
        [_soffice(), "--headless", "--norestore", "--nolockcheck",
         f"-env:UserInstallation=file://{profile}",
         "--convert-to", "doc", "--outdir", str(tmp_path), str(dirty_docx)],
        capture_output=True, timeout=120, check=False,
    )
    doc = tmp_path / "memo.doc"
    if not doc.is_file():
        pytest.skip("LibreOffice conversion did not produce a .doc")
    return doc


_TRACKED_DOC = """<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:ins w:id="1" w:author="Dave Editor" w:date="2024-05-01T10:00:00Z"><w:r><w:t>added text</w:t></w:r></w:ins>
<w:del w:id="2" w:author="Erin Reviewer" w:date="2024-05-02T11:00:00Z"><w:r><w:delText>gone</w:delText></w:r></w:del></w:p>
</w:body></w:document>"""
_COMMENTS = """<?xml version="1.0"?><w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:comment w:id="1" w:author="Frank Legal" w:initials="FL" w:date="2024-05-03T09:00:00Z"><w:p><w:r><w:t>check this clause</w:t></w:r></w:p></w:comment></w:comments>"""
_PEOPLE = """<?xml version="1.0"?><w15:people xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"><w15:person w15:author="Frank Legal"><w15:presenceInfo w15:providerId="AD" w15:userId="S-1-5-21-frank"/></w15:person></w15:people>"""


@pytest.fixture
def tracked_docx(tmp_path):
    path = tmp_path / "tracked.docx"
    ct = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/></Types>')
    rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", _TRACKED_DOC)
        z.writestr("word/comments.xml", _COMMENTS)
        z.writestr("word/people.xml", _PEOPLE)
    return path


@pytest.fixture
def dirty_odt(tmp_path):
    path = tmp_path / "notes.odt"
    meta = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" office:version="1.3"><office:meta>'
        "<meta:initial-creator>Erin Writer</meta:initial-creator>"
        "<dc:creator>Frank Editor</dc:creator>"
        "<meta:generator>LibreOffice/7.6</meta:generator>"
        "<meta:editing-cycles>12</meta:editing-cycles>"
        "<dc:title>Board Notes</dc:title>"
        "</office:meta></office:document-meta>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        z.writestr("content.xml", '<?xml version="1.0"?><doc/>')
        z.writestr("meta.xml", meta)
    return path


@pytest.fixture
def dirty_jpg(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(_JPEG_1PX)
    if exiftool_present():
        subprocess.run(
            [
                "exiftool", "-overwrite_original",
                "-Artist=Alice Example", "-Copyright=Acme Corp",
                "-Make=Canon", "-Model=Canon EOS R5", "-Software=Acme Photo 3.1",
                "-GPSLatitude=41.015137", "-GPSLatitudeRef=N",
                "-GPSLongitude=28.979530", "-GPSLongitudeRef=E",
                "-DateTimeOriginal=2024:03:10 14:22:00",
                str(path),
            ],
            check=True, capture_output=True,
        )
    return path


@pytest.fixture
def dirty_tree(tmp_path, dirty_pdf, dirty_docx, dirty_jpg):
    """A directory with the three dirty files plus one in a subdirectory."""
    root = tmp_path / "tree"
    sub = root / "sub"
    sub.mkdir(parents=True)
    shutil.copy(dirty_pdf, root / "forecast.pdf")
    shutil.copy(dirty_docx, root / "memo.docx")
    shutil.copy(dirty_jpg, root / "photo.jpg")
    shutil.copy(dirty_docx, sub / "memo2.docx")
    (root / "notes.txt").write_text("not a supported type")
    return root
