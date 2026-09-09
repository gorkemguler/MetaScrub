from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

from ..config import CleanConfig, ODF_EXTENSIONS, OOXML_EXTENSIONS
from ..models import FieldChange
from .base import new_result

# --- OOXML (docx/xlsx/pptx) --------------------------------------------------

_NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

# Package parts that are pure metadata / preview — removed outright, along
# with their relationship entries and content-type overrides.
_OOXML_META_PARTS = ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml")
_OOXML_META_PREFIXES = ("docProps/thumbnail",)

# Human-readable field name for each core.xml / app.xml tag we report.
_CORE_LABELS = {
    f"{{{_NS['dc']}}}creator": "creator",
    f"{{{_NS['dc']}}}title": "title",
    f"{{{_NS['dc']}}}subject": "subject",
    f"{{{_NS['dc']}}}description": "description",
    f"{{{_NS['cp']}}}lastModifiedBy": "lastModifiedBy",
    f"{{{_NS['cp']}}}keywords": "keywords",
    f"{{{_NS['cp']}}}revision": "revision",
    f"{{{_NS['cp']}}}category": "category",
    f"{{{_NS['cp']}}}contentStatus": "contentStatus",
    f"{{{_NS['cp']}}}lastPrinted": "lastPrinted",
    f"{{{_NS['dcterms']}}}created": "created",
    f"{{{_NS['dcterms']}}}modified": "modified",
}
_APP_LEAK_TAGS = ("Company", "Manager", "Template", "HyperlinkBase")

# Fixed timestamp for every rebuilt zip member — the real per-file mtimes
# are themselves a (small) leak.
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

# --- OpenDocument (odt/ods/odp) --------------------------------------------

_ODF_META_PART = "meta.xml"
_ODF_OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
_ODF_META_NS = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
_ODF_EMPTY_META = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    f'<office:document-meta xmlns:office="{_ODF_OFFICE_NS}" '
    f'xmlns:meta="{_ODF_META_NS}" xmlns:dc="{_NS["dc"]}" office:version="1.3">'
    "<office:meta>{kept}</office:meta></office:document-meta>"
)


class OfficeEngine:
    name = "office"
    extensions = OOXML_EXTENSIONS | ODF_EXTENSIONS

    def probe(self, path: str) -> list[FieldChange]:
        ext = _ext(path)
        try:
            with zipfile.ZipFile(path) as zf:
                names = set(zf.namelist())
                if ext in OOXML_EXTENSIONS:
                    return _probe_ooxml(zf, names)
                return _probe_odf(zf, names)
        except zipfile.BadZipFile:
            return []

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        ext = _ext(src)
        with zipfile.ZipFile(src) as zin:
            names = zin.namelist()
            nameset = set(names)
            if ext in OOXML_EXTENSIONS:
                removed, rewrites, drops = _plan_ooxml(zin, nameset, cfg)
            else:
                removed, rewrites, drops = _plan_odf(zin, nameset, cfg)

            with zipfile.ZipFile(dst, "w") as zout:
                for info in zin.infolist():
                    if info.filename in drops:
                        continue
                    data = rewrites.get(info.filename)
                    if data is None:
                        data = zin.read(info.filename)
                    new_info = zipfile.ZipInfo(info.filename, date_time=_ZIP_EPOCH)
                    new_info.compress_type = info.compress_type
                    new_info.external_attr = info.external_attr
                    zout.writestr(new_info, data)

        kept = sorted({fc.field for fc in removed if fc.after is not None})
        removed = [fc for fc in removed if fc.after is None]
        return new_result(src, dst, self.name, "cleaned", removed=removed, kept=kept)


# --- OOXML helpers ---------------------------------------------------------


def _probe_ooxml(zf: zipfile.ZipFile, names: set[str]) -> list[FieldChange]:
    rows: list[FieldChange] = []
    if "docProps/core.xml" in names:
        rows += _core_fields(zf.read("docProps/core.xml"))
    if "docProps/app.xml" in names:
        rows += _app_fields(zf.read("docProps/app.xml"))
    if "docProps/custom.xml" in names:
        rows += _custom_fields(zf.read("docProps/custom.xml"))
    if any(n.startswith(p) for n in names for p in _OOXML_META_PREFIXES):
        rows.append(FieldChange("docProps", "thumbnail", "<embedded preview image>"))
    rows += _rsid_fields(zf, names)
    return rows


def _plan_ooxml(zf: zipfile.ZipFile, names: set[str], cfg: CleanConfig):
    removed: list[FieldChange] = []
    rewrites: dict[str, bytes] = {}
    drops: set[str] = set()

    keep_core: dict[str, str] = {}
    if "docProps/core.xml" in names:
        for fc in _core_fields(zf.read("docProps/core.xml")):
            if cfg.wants_field(fc.field):
                keep_core[fc.field] = fc.before
                removed.append(FieldChange(fc.namespace, fc.field, fc.before, after=fc.before))
            else:
                removed.append(fc)
    if "docProps/app.xml" in names:
        removed += [fc for fc in _app_fields(zf.read("docProps/app.xml")) if not cfg.wants_field(fc.field)]
    if "docProps/custom.xml" in names:
        removed += _custom_fields(zf.read("docProps/custom.xml"))

    for part in _OOXML_META_PARTS:
        if part in names:
            drops.add(part)
    for n in names:
        if any(n.startswith(p) for p in _OOXML_META_PREFIXES):
            drops.add(n)
            removed.append(FieldChange("docProps", "thumbnail", "<embedded preview image>"))

    # Re-add a minimal core.xml when the user asked to keep some fields.
    if keep_core:
        rewrites["docProps/core.xml"] = _build_core_xml(keep_core)
        drops.discard("docProps/core.xml")

    # Prune relationships + content-type overrides that now dangle.
    if "_rels/.rels" in names:
        pruned = _prune_rels(zf.read("_rels/.rels"), drops)
        if pruned is not None:
            rewrites["_rels/.rels"] = pruned
    if "[Content_Types].xml" in names:
        pruned = _prune_content_types(zf.read("[Content_Types].xml"), drops)
        if pruned is not None:
            rewrites["[Content_Types].xml"] = pruned

    # Best-effort: drop Word revision-save-id fingerprints from settings.
    for settings_part in ("word/settings.xml", "ppt/presProps.xml"):
        if settings_part in names:
            cleaned, hit = _strip_rsids(zf.read(settings_part))
            if hit:
                rewrites[settings_part] = cleaned
                removed.append(FieldChange(settings_part, "w:rsids", "<revision save IDs>"))

    return removed, rewrites, drops


def _core_fields(data: bytes) -> list[FieldChange]:
    rows: list[FieldChange] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return rows
    for el in root:
        label = _CORE_LABELS.get(el.tag, el.tag.rsplit("}", 1)[-1])
        text = (el.text or "").strip()
        if text:
            rows.append(FieldChange("docProps/core", label, text))
    return rows


def _app_fields(data: bytes) -> list[FieldChange]:
    rows: list[FieldChange] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return rows
    for el in root:
        tag = el.tag.rsplit("}", 1)[-1]
        text = (el.text or "").strip()
        if tag in _APP_LEAK_TAGS and text:
            rows.append(FieldChange("docProps/app", tag, text))
    return rows


def _custom_fields(data: bytes) -> list[FieldChange]:
    rows: list[FieldChange] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return rows
    for el in root:
        name = el.get("name") or "property"
        value = "".join(el.itertext()).strip()
        rows.append(FieldChange("docProps/custom", name, value or "<set>"))
    return rows


def _rsid_fields(zf: zipfile.ZipFile, names: set[str]) -> list[FieldChange]:
    for part in ("word/settings.xml", "ppt/presProps.xml"):
        if part in names:
            _, hit = _strip_rsids(zf.read(part))
            if hit:
                return [FieldChange(part, "w:rsids", "<revision save IDs>")]
    return []


def _build_core_xml(kept: dict[str, str]) -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<cp:coreProperties '
        f'xmlns:cp="{_NS["cp"]}" xmlns:dc="{_NS["dc"]}" '
        f'xmlns:dcterms="{_NS["dcterms"]}" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
    ]
    tagmap = {
        "title": ("dc", "title"), "subject": ("dc", "subject"),
        "description": ("dc", "description"), "creator": ("dc", "creator"),
        "keywords": ("cp", "keywords"), "category": ("cp", "category"),
        "contentStatus": ("cp", "contentStatus"),
    }
    for field, value in kept.items():
        if field not in tagmap:
            continue
        prefix, tag = tagmap[field]
        parts.append(f"<{prefix}:{tag}>{_xml_escape(value)}</{prefix}:{tag}>")
    parts.append("</cp:coreProperties>")
    return "".join(parts).encode("utf-8")


def _prune_rels(data: bytes, drops: set[str]) -> bytes | None:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    ns = f"{{{_NS['pr']}}}"
    changed = False
    for rel in list(root):
        target = (rel.get("Target") or "").lstrip("/")
        if target in drops or any(target.startswith(p) for p in _OOXML_META_PREFIXES):
            root.remove(rel)
            changed = True
    if not changed:
        return None
    ET.register_namespace("", _NS["pr"])
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(root, encoding="utf-8")


def _prune_content_types(data: bytes, drops: set[str]) -> bytes | None:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    changed = False
    for override in list(root):
        if not override.tag.endswith("}Override"):
            continue
        part = (override.get("PartName") or "").lstrip("/")
        if part in drops or any(part.startswith(p) for p in _OOXML_META_PREFIXES):
            root.remove(override)
            changed = True
    if not changed:
        return None
    ET.register_namespace("", _NS["ct"])
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(root, encoding="utf-8")


_RSIDS_BLOCK = re.compile(rb"<w:rsids>.*?</w:rsids>", re.DOTALL)
_PROOFSTATE = re.compile(rb"<w:proofState\b[^>]*/>")


def _strip_rsids(data: bytes) -> tuple[bytes, bool]:
    new = _RSIDS_BLOCK.sub(b"", data)
    new = _PROOFSTATE.sub(b"", new)
    return new, new != data


# --- ODF helpers ---------------------------------------------------------


def _probe_odf(zf: zipfile.ZipFile, names: set[str]) -> list[FieldChange]:
    if _ODF_META_PART not in names:
        return []
    return _odf_meta_fields(zf.read(_ODF_META_PART))


def _plan_odf(zf: zipfile.ZipFile, names: set[str], cfg: CleanConfig):
    removed: list[FieldChange] = []
    rewrites: dict[str, bytes] = {}
    if _ODF_META_PART not in names:
        return removed, rewrites, set()

    kept_xml: list[str] = []
    for fc in _odf_meta_fields(zf.read(_ODF_META_PART)):
        if cfg.wants_field(fc.field):
            removed.append(FieldChange(fc.namespace, fc.field, fc.before, after=fc.before))
            kept_xml.append(f"<dc:{fc.field}>{_xml_escape(fc.before)}</dc:{fc.field}>")
        else:
            removed.append(fc)
    rewrites[_ODF_META_PART] = _ODF_EMPTY_META.format(kept="".join(kept_xml)).encode("utf-8")
    return removed, rewrites, set()


def _odf_meta_fields(data: bytes) -> list[FieldChange]:
    rows: list[FieldChange] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return rows
    meta = root.find(f"{{{_ODF_META_NS}}}meta")
    if meta is None:
        return rows
    for el in meta:
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "document-statistic":
            value = ", ".join(f"{k.rsplit('}', 1)[-1]}={v}" for k, v in el.attrib.items())
        else:
            value = "".join(el.itertext()).strip()
        if value:
            rows.append(FieldChange("meta.xml", tag, value))
    return rows


# --- shared --------------------------------------------------------------


def _ext(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
