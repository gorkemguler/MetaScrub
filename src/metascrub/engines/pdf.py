from __future__ import annotations

import secrets

import pikepdf

from ..config import CleanConfig
from ..models import FieldChange
from .base import new_result

# Catalog-level keys that carry application-private or identifying data
# rather than page content. Removed wholesale.
_CATALOG_PRIVATE_KEYS = ("/Metadata", "/PieceInfo")

# Annotation entries that identify the reviewer or when they worked, as
# opposed to the annotation's visible content (/Contents, /RC) which is
# left alone — MetaScrub scrubs metadata, not content.
_ANNOT_IDENTITY_KEYS = ("/T", "/M", "/CreationDate")

# Prettify the Clark-notation ({uri}local) keys pikepdf yields for XMP
# back into the conventional prefix:local form for the report.
_XMP_NS = {
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/xap/1.0/mm/": "xmpMM",
    "http://ns.adobe.com/xap/1.0/rights/": "xmpRights",
    "http://ns.adobe.com/pdf/1.3/": "pdf",
    "http://ns.adobe.com/pdfx/1.3/": "pdfx",
    "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/": "Iptc4xmpCore",
    "http://ns.adobe.com/exif/1.0/": "exif",
    "http://ns.adobe.com/tiff/1.0/": "tiff",
}


def _pretty_xmp_key(key: str) -> str:
    if key.startswith("{") and "}" in key:
        uri, _, local = key[1:].partition("}")
        return f"{_XMP_NS.get(uri, uri)}:{local}"
    return key


class _Encrypted(Exception):
    """Raised when the PDF is encrypted and the supplied password (if any)
    doesn't open it. `.wrong_password` distinguishes 'no password given'
    from 'given password rejected'."""

    def __init__(self, wrong_password: bool) -> None:
        self.wrong_password = wrong_password


def _open(path: str, cfg: CleanConfig | None):
    password = (cfg.pdf_password if cfg else None) or ""
    try:
        return pikepdf.open(path, password=password)
    except pikepdf.PasswordError as exc:  # type: ignore[attr-defined]
        raise _Encrypted(wrong_password=bool(password)) from exc


class PdfEngine:
    name = "pdf"
    extensions = frozenset({"pdf"})

    # ------------------------------------------------------------------ probe

    def probe(self, path: str, cfg: CleanConfig | None = None) -> list[FieldChange]:
        try:
            pdf = _open(path, cfg)
        except _Encrypted as enc:
            note = "wrong --password" if enc.wrong_password else "supply --password to inspect"
            return [FieldChange("PDF", "encryption", f"<encrypted — {note}>")]

        rows: list[FieldChange] = []
        with pdf:
            info = pdf.trailer.get("/Info")
            if info is not None:
                for key, value in info.items():
                    rows.append(FieldChange("PDF Info", str(key).lstrip("/"), _str(value)))

            rows.extend(_probe_xmp(pdf))

            if "/PieceInfo" in pdf.Root:
                rows.append(FieldChange("PDF", "PieceInfo", "<application-private data>"))
            for n, page in enumerate(pdf.pages, start=1):
                if "/PieceInfo" in page.obj:
                    rows.append(FieldChange("PDF", f"Page {n} /PieceInfo", "<application-private data>"))
                if "/Metadata" in page.obj:
                    rows.append(FieldChange("XMP", f"Page {n} /Metadata", "<embedded XMP packet>"))

            rows.extend(_probe_annots(pdf))
            rows.extend(_probe_attachments(pdf))
        return rows

    # ------------------------------------------------------------------ strip

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        try:
            pdf = _open(src, cfg)
        except _Encrypted as enc:
            if enc.wrong_password:
                return new_result(src, None, self.name, "error",
                                  error="wrong --password for this encrypted PDF")
            return new_result(src, None, self.name, "skipped",
                              reason="encrypted PDF — pass --password to scrub it")

        with pdf:
            signed = _signature_reason(pdf)
            if signed:
                return new_result(src, None, self.name, "skipped", reason=signed)

            removed: list[FieldChange] = []
            kept: list[str] = []
            was_encrypted = bool(pdf.is_encrypted)

            # --- /Info dictionary ---
            info = pdf.trailer.get("/Info")
            if info is not None:
                for key in list(info.keys()):
                    leaf = str(key).lstrip("/")
                    old = _str(info[key])
                    if cfg.wants_field(leaf):
                        kept.append(leaf)
                        continue
                    del info[key]
                    removed.append(FieldChange("PDF Info", leaf, old))
                if len(info.keys()) == 0:
                    del pdf.trailer["/Info"]

            # --- XMP packet(s) ---
            for row in _probe_xmp(pdf):
                removed.append(FieldChange(row.namespace, row.field, row.before))
            if "/Metadata" in pdf.Root:
                del pdf.Root["/Metadata"]

            # --- catalog + page private data ---
            for key in _CATALOG_PRIVATE_KEYS:
                if key == "/Metadata":
                    continue  # already handled
                if key in pdf.Root:
                    del pdf.Root[key]
                    removed.append(FieldChange("PDF", key.lstrip("/"), "<application-private data>"))
            for n, page in enumerate(pdf.pages, start=1):
                for key in ("/PieceInfo", "/Metadata"):
                    if key in page.obj:
                        del page.obj[key]
                        removed.append(FieldChange("PDF", f"Page {n} {key.lstrip('/')}", "<removed>"))

            # --- annotation authors / dates + embedded-file metadata ---
            removed.extend(_strip_annots(pdf))
            removed.extend(_strip_attachments(pdf))

            # --- document /ID ---
            # A full rewrite already drops the original arbitrary /ID.
            # --strip-pdf-id goes further: a fresh random ID on every run,
            # so two scrubbed copies of the same file don't even share
            # that. (QPDF's non-deterministic ID only varies at
            # one-second granularity, so set it explicitly.)
            if cfg.strip_pdf_id:
                if pdf.trailer.get("/ID") is not None:
                    removed.append(FieldChange("PDF", "ID", "<document identifier — replaced with a random one>"))
                pdf.trailer.ID = pikepdf.Array(
                    [pikepdf.String(secrets.token_bytes(16)), pikepdf.String(secrets.token_bytes(16))]
                )

            save_kwargs = dict(
                fix_metadata_version=False,
                deterministic_id=not cfg.strip_pdf_id,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
            )
            # A full rewrite (not an incremental update) so removed values
            # can't be recovered from a superseded xref section. An
            # encrypted input becomes an unencrypted cleaned copy — noted
            # in the result.
            pdf.save(dst, **save_kwargs)

        result = new_result(src, dst, self.name, "cleaned", removed=removed, kept=sorted(set(kept)))
        if was_encrypted:
            result.reason = "input was encrypted; the cleaned copy is not"
        return result


# --------------------------------------------------------------------- helpers


def _probe_xmp(pdf: pikepdf.Pdf) -> list[FieldChange]:
    if "/Metadata" not in pdf.Root:
        return []
    rows: list[FieldChange] = []
    try:
        meta = pdf.open_metadata(set_pikepdf_as_editor=False)
        for key in meta:
            rows.append(FieldChange("XMP", _pretty_xmp_key(str(key)), _str(meta[key])))
    except Exception:
        # Malformed / unparseable XMP still gets removed by strip(); just
        # report its presence here.
        rows.append(FieldChange("XMP", "<xmp packet>", "<embedded XMP metadata>"))
    if not rows:
        rows.append(FieldChange("XMP", "<xmp packet>", "<embedded XMP metadata>"))
    return rows


def _iter_annots(pdf: pikepdf.Pdf):
    """Yield (page_number, annotation_dict) for every non-widget markup
    annotation. Widget annotations are form fields — their /T is the field
    name, not an author, so they're left alone."""
    for n, page in enumerate(pdf.pages, start=1):
        annots = page.obj.get("/Annots")
        if annots is None:
            continue
        for annot in list(annots):
            try:
                subtype = str(annot.get("/Subtype"))
            except Exception:
                subtype = ""
            if subtype == "/Widget":
                continue
            yield n, annot


def _probe_annots(pdf: pikepdf.Pdf) -> list[FieldChange]:
    rows: list[FieldChange] = []
    for n, annot in _iter_annots(pdf):
        for key in _ANNOT_IDENTITY_KEYS:
            if key in annot:
                rows.append(FieldChange("PDF Annotation", f"Page {n} {key.lstrip('/')}", _str(annot[key])))
        popup = annot.get("/Popup")
        if popup is not None and "/T" in popup:
            rows.append(FieldChange("PDF Annotation", f"Page {n} Popup T", _str(popup["/T"])))
    return rows


def _strip_annots(pdf: pikepdf.Pdf) -> list[FieldChange]:
    removed: list[FieldChange] = []
    for n, annot in _iter_annots(pdf):
        for key in _ANNOT_IDENTITY_KEYS:
            if key in annot:
                old = _str(annot[key])
                del annot[key]
                removed.append(FieldChange("PDF Annotation", f"Page {n} {key.lstrip('/')}", old))
        popup = annot.get("/Popup")
        if popup is not None and "/T" in popup:
            old = _str(popup["/T"])
            del popup["/T"]
            removed.append(FieldChange("PDF Annotation", f"Page {n} Popup T", old))
    return removed


def _iter_filespecs(pdf: pikepdf.Pdf):
    """Every embedded-file specification dict reachable from the name tree
    or an /AF (associated files) array, de-duplicated by object id."""
    seen: set = set()

    def _emit(obj):
        try:
            key = obj.objgen
        except Exception:
            key = id(obj)
        if key in seen:
            return
        seen.add(key)
        yield_list.append(obj)

    yield_list: list = []

    def _walk_tree(node):
        try:
            names = node.get("/Names")
        except Exception:
            names = None
        if names is not None:
            arr = list(names)
            for i in range(1, len(arr), 2):
                _emit(arr[i])
        kids = node.get("/Kids") if hasattr(node, "get") else None
        if kids is not None:
            for kid in list(kids):
                _walk_tree(kid)

    names_root = pdf.Root.get("/Names")
    if names_root is not None:
        ef = names_root.get("/EmbeddedFiles")
        if ef is not None:
            _walk_tree(ef)

    for container in (pdf.Root, *(p.obj for p in pdf.pages)):
        af = container.get("/AF")
        if af is not None:
            for spec in list(af):
                _emit(spec)

    return yield_list


def _filespec_name(spec) -> str:
    for key in ("/UF", "/F"):
        if key in spec:
            return _str(spec[key])
    return "<embedded file>"


def _probe_attachments(pdf: pikepdf.Pdf) -> list[FieldChange]:
    rows: list[FieldChange] = []
    for spec in _iter_filespecs(pdf):
        name = _filespec_name(spec)
        if "/Desc" in spec:
            rows.append(FieldChange("PDF Attachment", f"{name} Desc", _str(spec["/Desc"])))
        ef = spec.get("/EF")
        if ef is None:
            continue
        for k in list(ef.keys()):
            stream = ef.get(k)
            params = stream.get("/Params") if stream is not None else None
            if params is None:
                continue
            for pk in ("/CreationDate", "/ModDate"):
                if pk in params:
                    rows.append(FieldChange("PDF Attachment", f"{name} {pk.lstrip('/')}", _str(params[pk])))
    return rows


def _strip_attachments(pdf: pikepdf.Pdf) -> list[FieldChange]:
    """Strip the identifying metadata *on* an embedded file (its
    description and original timestamps) while keeping the attachment
    itself — the file is content, its provenance is metadata."""
    removed: list[FieldChange] = []
    for spec in _iter_filespecs(pdf):
        name = _filespec_name(spec)
        if "/Desc" in spec:
            old = _str(spec["/Desc"])
            del spec["/Desc"]
            removed.append(FieldChange("PDF Attachment", f"{name} Desc", old))
        ef = spec.get("/EF")
        if ef is None:
            continue
        for k in list(ef.keys()):
            stream = ef.get(k)
            params = stream.get("/Params") if stream is not None else None
            if params is None:
                continue
            for pk in ("/CreationDate", "/ModDate"):
                if pk in params:
                    old = _str(params[pk])
                    del params[pk]
                    removed.append(FieldChange("PDF Attachment", f"{name} {pk.lstrip('/')}", old))
    return removed


def _signature_reason(pdf: pikepdf.Pdf) -> str | None:
    """Non-None when the PDF carries a digital signature — scrubbing would
    invalidate it, so we skip rather than silently break it."""
    acro = pdf.Root.get("/AcroForm")
    if acro is not None:
        sig_flags = acro.get("/SigFlags")
        try:
            if sig_flags is not None and int(sig_flags) & 1:
                return "signed PDF — scrubbing would invalidate the signature"
        except (TypeError, ValueError):
            pass
    if "/Perms" in pdf.Root:
        return "signed PDF (/Perms present) — scrubbing would invalidate the signature"
    return None


def _str(value: object) -> str:
    try:
        return str(value)
    except Exception:
        return "<unreadable>"
