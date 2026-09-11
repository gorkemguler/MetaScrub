#!/usr/bin/env python3
"""MetaCLS Drop -- a persistent drag-and-drop window (GTK3), the Linux
counterpart to platform/windows/MetaCLS-drop.ps1 and
platform/macos/metacls_drop.py. Styled to match the project's dark/green
branding (see assets/banner.svg, assets/desktop-apps.svg).

    python3 metacls_drop_gtk.py

Drop PDF / Office / image / SVG files onto the window and they're
scrubbed IN PLACE with `metacls clean --in-place`; results show in the
log below, newest at the bottom. Nothing leaves your machine.

Needs GTK3 + PyGObject (`python3-gi` / `gir1.2-gtk-3.0` on Debian/Ubuntu,
`python3-gobject` on Fedora, `python-gobject` on Arch, usually already
present on GNOME/GTK-based desktops). `metacls` must be installed and
reachable (`pip install metacls` / `pipx install metacls`).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

# The brand palette from assets/banner.svg / assets/desktop-apps.svg.
BG = "#0c1110"
PANEL = "#13201c"
BORDER = "#22332e"
GREEN = "#2dd4a7"
GREEN_STRONG = "#34d399"
INK = "#e9efed"
MUTED = "#93a5a0"
DIM = "#6f8480"
BAD = "#f87171"

CSS = f"""
window {{ background-color: {BG}; }}
.brand-meta {{ color: {INK}; font-weight: 800; font-size: 22px; }}
.brand-cls {{ color: {GREEN_STRONG}; font-weight: 800; font-size: 22px; }}
.tagline {{ color: {DIM}; font-size: 11px; }}
.dropzone {{
    border: 2px dashed rgba(45, 212, 167, 0.55);
    border-radius: 14px;
    background-color: transparent;
}}
.hint {{ color: {INK}; font-weight: 700; font-size: 14px; }}
.subhint {{ color: {DIM}; font-size: 11px; }}
scrolledwindow, textview, textview text {{
    background-color: {PANEL};
    color: {MUTED};
}}
"""


def find_metacls() -> str | None:
    env = os.environ.get("METACLS")
    if env and shutil.which(env):
        return env
    found = shutil.which("metacls")
    if found:
        return found
    candidate = os.path.expanduser("~/.local/bin/metacls")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return None


def scrub_paths(paths: list[str]) -> list[str]:
    metacls = find_metacls()
    if metacls is None:
        return ["! metacls not found on PATH -- pip install metacls (or pipx install metacls)"]

    lines = []
    ok = fail = 0
    for path in paths:
        if not os.path.isfile(path):
            continue
        result = subprocess.run(
            [metacls, "clean", path, "--in-place", "--yes", "--no-json-report", "--no-html-report"],
            capture_output=True,
        )
        name = os.path.basename(path)
        if result.returncode == 0:
            ok += 1
            lines.append(f"ok    {name}")
        else:
            fail += 1
            lines.append(f"FAIL  {name}  (exit {result.returncode})")
    lines.append(f"-- scrubbed {ok}, failed {fail} --")
    return lines


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


class DropIcon(Gtk.DrawingArea):
    """The wipe-stroke + document icon motif, matching assets/desktop-apps.svg."""

    def __init__(self):
        super().__init__()
        self.set_size_request(160, 70)
        self.connect("draw", self._draw)

    def _draw(self, _widget, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        cx = w / 2

        lines = [(46, 0.9), (36, 0.6), (24, 0.35)]
        ly = h / 2 + 14
        for width, alpha in lines:
            r, g, b = _hex_to_rgb(GREEN)
            cr.set_source_rgba(r, g, b, alpha)
            cr.set_line_width(6)
            cr.set_line_cap(1)  # round
            x0 = cx - 55
            cr.move_to(x0, ly)
            cr.line_to(x0 + width, ly)
            cr.stroke()
            ly -= 13

        doc_w, doc_h = 32, 42
        doc_x = cx + 6
        doc_y = h / 2 - doc_h / 2 - 4
        r, g, b = _hex_to_rgb(BG)
        cr.set_source_rgb(r, g, b)
        _rounded_rect(cr, doc_x, doc_y, doc_w, doc_h, 4)
        cr.fill_preserve()
        r, g, b = _hex_to_rgb(GREEN_STRONG)
        cr.set_source_rgb(r, g, b)
        cr.set_line_width(2)
        cr.stroke()

        cr.move_to(doc_x + doc_w - 10, doc_y)
        cr.line_to(doc_x + doc_w, doc_y + 10)
        cr.line_to(doc_x + doc_w - 10, doc_y + 10)
        cr.close_path()
        cr.fill()
        return False


def _rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -90 * 3.14159 / 180, 0)
    cr.arc(x + w - r, y + h - r, r, 0, 90 * 3.14159 / 180)
    cr.arc(x + r, y + h - r, r, 90 * 3.14159 / 180, 180 * 3.14159 / 180)
    cr.arc(x + r, y + r, r, 180 * 3.14159 / 180, 270 * 3.14159 / 180)
    cr.close_path()


class DropWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="MetaCLS")
        self.set_default_size(600, 560)
        self.set_position(Gtk.WindowPosition.CENTER)

        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", True)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.set_border_width(20)
        self.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header.set_halign(Gtk.Align.CENTER)
        wordmark = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        wordmark.set_halign(Gtk.Align.CENTER)
        meta = Gtk.Label(label="meta")
        meta.get_style_context().add_class("brand-meta")
        cls = Gtk.Label(label="cls")
        cls.get_style_context().add_class("brand-cls")
        wordmark.pack_start(meta, False, False, 0)
        wordmark.pack_start(cls, False, False, 0)
        header.pack_start(wordmark, False, False, 0)
        tagline = Gtk.Label(label="strip the metadata · keep the document")
        tagline.get_style_context().add_class("tagline")
        header.pack_start(tagline, False, False, 0)
        root.pack_start(header, False, False, 0)

        zone = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        zone.get_style_context().add_class("dropzone")
        zone.set_size_request(-1, 200)
        zone.set_valign(Gtk.Align.CENTER)
        icon = DropIcon()
        icon.set_halign(Gtk.Align.CENTER)
        icon.set_valign(Gtk.Align.CENTER)
        zone.pack_start(icon, True, True, 0)
        hint = Gtk.Label(label="Drag & drop to scrub")
        hint.get_style_context().add_class("hint")
        zone.pack_start(hint, False, False, 0)
        subhint = Gtk.Label(label="Scrubbed in place -- nothing else leaves this window.")
        subhint.get_style_context().add_class("subhint")
        zone.pack_start(subhint, False, False, 4)
        root.pack_start(zone, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_buffer = self.log_view.get_buffer()
        self.tag_ok = self.log_buffer.create_tag("ok", foreground=GREEN_STRONG)
        self.tag_fail = self.log_buffer.create_tag("fail", foreground=BAD)
        self.tag_muted = self.log_buffer.create_tag("muted", foreground=MUTED)
        self._append_line("Drop a file above to see results here.", self.tag_muted)
        scroller.add(self.log_view)
        root.pack_start(scroller, True, True, 0)

        targets = Gtk.TargetList.new([])
        targets.add_uri_targets(0)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_set_target_list(targets)
        self.connect("drag-data-received", self._on_drop)
        self.connect("destroy", Gtk.main_quit)

    def _append_line(self, text: str, tag) -> None:
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert_with_tags(end, text + "\n", tag)

    def _append_results(self, lines: list[str]) -> None:
        for line in lines:
            if line.startswith("ok"):
                tag = self.tag_ok
            elif line.startswith("FAIL") or line.startswith("!"):
                tag = self.tag_fail
            else:
                tag = self.tag_muted
            self._append_line(line, tag)
        mark = self.log_buffer.create_mark(None, self.log_buffer.get_end_iter(), False)
        self.log_view.scroll_to_mark(mark, 0, False, 0, 0)

    def _on_drop(self, _widget, _ctx, _x, _y, data, _info, time):
        uris = data.get_uris() or []
        paths = []
        for uri in uris:
            parsed = urlparse(uri)
            if parsed.scheme == "file":
                paths.append(unquote(parsed.path))
        if paths:
            self._append_results(scrub_paths(paths))
        Gtk.drag_finish(_ctx, True, False, time)


def main() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode("utf-8"))
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    win = DropWindow()
    win.show_all()
    GLib.set_application_name("MetaCLS")
    Gtk.main()


if __name__ == "__main__":
    main()
