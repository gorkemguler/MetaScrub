from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from metascrub.config import CleanConfig
from metascrub.engines.svg import SvgEngine

_DIRTY_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Created with Inkscape (http://www.inkscape.org/) -->
<svg xmlns="http://www.w3.org/2000/svg" xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:cc="http://creativecommons.org/ns#" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
  xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0"
  xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
  width="100" height="100" viewBox="0 0 100 100"
  inkscape:version="1.1" sodipodi:docname="secret-plan.svg">
  <sodipodi:namedview id="nv1" inkscape:current-layer="layer1" inkscape:window-maximized="1"/>
  <metadata id="metadata1">
    <rdf:RDF><cc:Work rdf:about="">
      <dc:title>Acme Secret Logo</dc:title>
      <dc:creator><cc:Agent><dc:title>Alice Example</dc:title></cc:Agent></dc:creator>
    </cc:Work></rdf:RDF>
  </metadata>
  <g inkscape:label="Layer 1" inkscape:groupmode="layer" id="layer1">
    <rect x="10" y="10" width="80" height="80" fill="#2dd4a7"/>
  </g>
</svg>
"""


@pytest.fixture
def dirty_svg(tmp_path):
    p = tmp_path / "logo.svg"
    p.write_text(_DIRTY_SVG)
    return p


def test_probe_sees_metadata_and_editor_data(dirty_svg):
    fields = {r.field for r in SvgEngine().probe(str(dirty_svg))}
    assert "metadata" in fields
    assert "namedview" in fields
    assert "editor attributes" in fields


def test_strip_removes_metadata_keeps_drawing(dirty_svg, tmp_path):
    dst = tmp_path / "clean.svg"
    result = SvgEngine().strip(str(dirty_svg), str(dst), CleanConfig())
    assert result.status == "cleaned" and result.removed

    text = dst.read_text()
    assert "Alice Example" not in text
    assert "Acme Secret Logo" not in text
    assert "sodipodi" not in text and "inkscape" not in text
    assert "Created with Inkscape" not in text          # comment gone
    assert "<rect" in text and "#2dd4a7" in text          # drawing kept

    root = ET.fromstring(text)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"  # still a valid default-ns SVG
    assert SvgEngine().probe(str(dst)) == []


def test_source_not_modified(dirty_svg, tmp_path):
    before = dirty_svg.read_bytes()
    SvgEngine().strip(str(dirty_svg), str(tmp_path / "c.svg"), CleanConfig())
    assert dirty_svg.read_bytes() == before


def test_unparseable_svg_is_error(tmp_path):
    p = tmp_path / "broken.svg"
    p.write_text("<svg><g></svg>")  # mismatched tags
    result = SvgEngine().strip(str(p), str(tmp_path / "o.svg"), CleanConfig())
    assert result.status == "error"
