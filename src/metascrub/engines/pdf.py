from __future__ import annotations

import pikepdf

from ..config import CleanConfig
from ..models import FieldChange
from .base import new_result

# Catalog-level keys that carry application-private or identifying data
# rather than page content. Removed wholesale.
_CATALOG_PRIVATE_KEYS = ("/Metadata", "/PieceInfo")

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


class PdfEngine:
    name = "pdf"
    extensions = frozenset({"pdf"})

    # ------------------------------------------------------------------ probe

    def probe(self, path: str) -> list[FieldChange]:
        rows: list[FieldChange] = []
        with pikepdf.open(path) as pdf:
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
        return rows

    # ------------------------------------------------------------------ strip

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        with pikepdf.open(src) as pdf:
            signed = _signature_reason(pdf)
            if signed:
                return new_result(src, None, self.name, "skipped", reason=signed)

            removed: list[FieldChange] = []
            kept: list[str] = []

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

            # Full rewrite (not an incremental update) so values sitting in
            # superseded xref sections can't be recovered from the output.
            pdf.save(
                dst,
                fix_metadata_version=False,
                deterministic_id=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
            )

        result = new_result(src, dst, self.name, "cleaned", removed=removed, kept=sorted(set(kept)))
        return result


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
