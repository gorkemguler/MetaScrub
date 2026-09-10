from __future__ import annotations

from xml.etree import ElementTree as ET

from ..config import CleanConfig, SVG_EXTENSIONS
from ..models import FieldChange
from .base import new_result

_SVG = "http://www.w3.org/2000/svg"
_DC = "http://purl.org/dc/elements/1.1/"
_SODIPODI = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0"
_INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"
_ADOBE_PREFIXES = ("http://ns.adobe.com/",)

# Keep SVG as the default (unprefixed) namespace on re-serialisation so
# the output is `<svg xmlns=...>`, not `<svg:svg xmlns:svg=...>` (some
# renderers and inline-in-HTML use are picky). xlink stays prefixed
# because SVG attributes reference it as `xlink:href`.
_NS_PREFIXES = {
    "": _SVG,
    "xlink": "http://www.w3.org/1999/xlink",
}

# Editor-private namespaces whose elements/attributes carry authoring
# fingerprints, not drawing content.
_EXACT_JUNK_NS = (_SODIPODI, _INKSCAPE)


def _is_junk_ns(uri: str) -> bool:
    return uri in _EXACT_JUNK_NS or uri.startswith("http://ns.adobe.com/")


class SvgEngine:
    name = "svg"
    extensions = SVG_EXTENSIONS

    def probe(self, path: str, cfg: CleanConfig | None = None) -> list[FieldChange]:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            return []
        rows: list[FieldChange] = []

        for md in root.iter(f"{{{_SVG}}}metadata"):
            texts = [t.strip() for t in md.itertext() if t.strip()]
            rows.append(FieldChange("SVG", "metadata", "; ".join(texts)[:200] or "<RDF metadata block>"))
            break
        for el in root.iter():
            if _ns_of(el.tag) in (_SODIPODI, _INKSCAPE):
                rows.append(FieldChange("SVG", _localname(el.tag), f"<{_prefix_of(el.tag)} element>"))
                break
        junk_attrs = sorted({
            _localname(k) for el in root.iter() for k in el.attrib
            if _is_junk_ns(_ns_of(k))
        })
        if junk_attrs:
            rows.append(FieldChange("SVG", "editor attributes", ", ".join(junk_attrs)[:200]))
        for el in root.iter():
            if any(_ns_of(el.tag).startswith(p) for p in _ADOBE_PREFIXES):
                rows.append(FieldChange("SVG", "Adobe Illustrator data", f"<{_localname(el.tag)}>"))
                break
        return rows

    def strip(self, src: str, dst: str, cfg: CleanConfig):
        try:
            tree = ET.parse(src)
        except ET.ParseError as exc:
            return new_result(src, None, self.name, "error", error=f"unparseable SVG: {exc}")
        root = tree.getroot()

        removed: list[FieldChange] = []

        # 1. drop <metadata>, sodipodi/inkscape/adobe elements
        _remove_matching(root, lambda el: _is_junk_element(el), removed)

        # 2. drop editor-private attributes anywhere
        for el in root.iter():
            for key in [k for k in el.attrib if _is_junk_ns(_ns_of(k))]:
                del el.attrib[key]
                removed.append(FieldChange("SVG", f"@{_localname(key)}", "<editor attribute>"))

        for prefix, uri in _NS_PREFIXES.items():
            ET.register_namespace(prefix, uri)

        data = ET.tostring(root, encoding="unicode")
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n')
            fh.write(data)
            if not data.endswith("\n"):
                fh.write("\n")

        # comments (Adobe "Generator:" etc.) are dropped for free — ET's
        # parser discards them — so note that separately isn't needed.
        return new_result(src, dst, self.name, "cleaned", removed=_dedupe(removed))


def _is_junk_element(el: ET.Element) -> bool:
    tag = el.tag
    if not isinstance(tag, str):
        return True  # comment / PI object
    if tag == f"{{{_SVG}}}metadata":
        return True
    return _is_junk_ns(_ns_of(tag))


def _remove_matching(parent: ET.Element, predicate, removed: list[FieldChange]) -> None:
    for child in list(parent):
        if predicate(child):
            label = _localname(child.tag) if isinstance(child.tag, str) else "comment"
            removed.append(FieldChange("SVG", label, f"<{label} removed>"))
            parent.remove(child)
        else:
            _remove_matching(child, predicate, removed)


def _ns_of(tag: str) -> str:
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


def _localname(tag) -> str:
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1]
    return str(tag)


def _prefix_of(tag: str) -> str:
    ns = _ns_of(tag)
    return {"": "svg", _SODIPODI: "sodipodi", _INKSCAPE: "inkscape"}.get(ns, ns)


def _dedupe(rows: list[FieldChange]) -> list[FieldChange]:
    seen = set()
    out = []
    for r in rows:
        key = (r.namespace, r.field)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
