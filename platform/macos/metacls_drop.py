#!/usr/bin/env python3
"""MetaCLS Drop — a persistent drag-and-drop window, the macOS
counterpart to platform/windows/MetaCLS-drop.ps1. Styled to match the
project's dark/green branding (see assets/banner.svg, assets/desktop-apps.svg).

    python3 metacls_drop.py

Drop PDF / Office / image / SVG files onto the window and they're
scrubbed IN PLACE with `metacls clean --in-place`; results show in the
log below, newest at the bottom. Nothing leaves your machine.

`metacls` must be installed and reachable (`pip install metacls` /
`pipx install metacls`). Needs PyObjC (`pyobjc-framework-Cocoa`); see
build-drop-app.sh, which sets that up in its own venv and wraps this
script into "MetaCLS Drop.app" so you don't need to think about it.
"""
from __future__ import annotations

import os
import shutil
import subprocess

import objc
from AppKit import (
    NSApp,
    NSAppearance,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelBorder,
    NSBezierPath,
    NSColor,
    NSDragOperationCopy,
    NSDragOperationNone,
    NSFilenamesPboardType,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSParagraphStyleAttributeName,
    NSRectFill,
    NSScrollView,
    NSTextAlignmentCenter,
    NSTextView,
    NSView,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSAttributedString, NSMakePoint, NSMutableParagraphStyle, NSObject
from PyObjCTools import AppHelper

# The brand palette from assets/banner.svg / assets/desktop-apps.svg.
BG = (0x0C / 255, 0x11 / 255, 0x10 / 255)
PANEL = (0x13 / 255, 0x20 / 255, 0x1C / 255)
BORDER = (0x22 / 255, 0x33 / 255, 0x2E / 255)
GREEN = (0x2D / 255, 0xD4 / 255, 0xA7 / 255)
GREEN_STRONG = (0x34 / 255, 0xD3 / 255, 0x99 / 255)
INK = (0xE9 / 255, 0xEF / 255, 0xED / 255)
MUTED = (0x93 / 255, 0xA5 / 255, 0xA0 / 255)
DIM = (0x6F / 255, 0x84 / 255, 0x80 / 255)
BAD = (0xF8 / 255, 0x71 / 255, 0x71 / 255)


def _c(rgb, alpha=1.0):
    r, g, b = rgb
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


def find_metacls() -> str | None:
    env = os.environ.get("METACLS")
    if env and shutil.which(env):
        return env
    found = shutil.which("metacls")
    if found:
        return found
    for candidate in (
        os.path.expanduser("~/.local/bin/metacls"),
        "/opt/homebrew/bin/metacls",
        "/usr/local/bin/metacls",
    ):
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


def _centered(text, font, color, rect):
    style = NSMutableParagraphStyle.alloc().init()
    style.setAlignment_(NSTextAlignmentCenter)
    attrs = {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: color,
        NSParagraphStyleAttributeName: style,
    }
    s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    h = s.size().height
    y = rect.origin.y + (rect.size.height - h) / 2
    s.drawInRect_(NSMakeRect(rect.origin.x, y, rect.size.width, h))


class BrandHeaderView(NSView):
    """The 'meta' + 'cls' wordmark and tagline, matching assets/banner.svg."""

    def drawRect_(self, dirty):
        b = self.bounds()
        name_font = NSFont.boldSystemFontOfSize_(22)
        meta = NSAttributedString.alloc().initWithString_attributes_(
            "meta", {NSFontAttributeName: name_font, NSForegroundColorAttributeName: _c(INK)}
        )
        cls = NSAttributedString.alloc().initWithString_attributes_(
            "cls", {NSFontAttributeName: name_font, NSForegroundColorAttributeName: _c(GREEN_STRONG)}
        )
        total_w = meta.size().width + cls.size().width
        x = (b.size.width - total_w) / 2
        top_y = b.size.height - 30
        meta.drawAtPoint_(NSMakePoint(x, top_y))
        cls.drawAtPoint_(NSMakePoint(x + meta.size().width, top_y))

        tagline_rect = NSMakeRect(0, b.size.height - 52, b.size.width, 16)
        _centered("strip the metadata · keep the document", NSFont.systemFontOfSize_(11), _c(DIM), tagline_rect)


class DropZoneView(NSView):
    """The dashed drop target, matching assets/desktop-apps.svg."""

    def drawRect_(self, dirty):
        b = self.bounds()
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(2, 2, b.size.width - 4, b.size.height - 4), 14, 14
        )
        path.setLineWidth_(2)
        path.setLineDash_count_phase_((8.0, 7.0), 2, 0.0)
        _c(GREEN, 0.55).setStroke()
        path.stroke()

        cx = b.size.width / 2
        # metadata "wipe" strokes, fading out -- echoes the banner motif.
        lines = [(60, 0.9), (46, 0.6), (30, 0.35)]
        ly = b.size.height / 2 + 18
        for width, alpha in lines:
            line = NSBezierPath.bezierPath()
            x0 = cx - 70
            line.moveToPoint_(NSMakePoint(x0, ly))
            line.lineToPoint_(NSMakePoint(x0 + width, ly))
            line.setLineWidth_(7)
            line.setLineCapStyle_(1)  # round
            _c(GREEN, alpha).setStroke()
            line.stroke()
            ly -= 16

        # a small document icon with a folded corner.
        doc_w, doc_h = 40, 52
        doc_x = cx + 10
        doc_y = b.size.height / 2 - doc_h / 2 + 6
        doc = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            NSMakeRect(doc_x, doc_y, doc_w, doc_h), 4, 4
        )
        _c(BG).setFill()
        doc.fill()
        _c(GREEN_STRONG).setStroke()
        doc.setLineWidth_(2)
        doc.stroke()
        fold = NSBezierPath.bezierPath()
        fold.moveToPoint_(NSMakePoint(doc_x + doc_w - 13, doc_y + doc_h))
        fold.lineToPoint_(NSMakePoint(doc_x + doc_w, doc_y + doc_h - 13))
        fold.lineToPoint_(NSMakePoint(doc_x + doc_w - 13, doc_y + doc_h - 13))
        fold.closePath()
        _c(GREEN_STRONG).setFill()
        fold.fill()

        _centered("Drag & drop to scrub", NSFont.boldSystemFontOfSize_(14), _c(INK),
                  NSMakeRect(0, 34, b.size.width, 20))
        _centered("Scrubbed in place -- nothing else leaves this window.",
                  NSFont.systemFontOfSize_(11), _c(DIM), NSMakeRect(0, 14, b.size.width, 16))


class RootView(NSView):
    """The window's whole content view: dark background, and the Finder
    file-drag target (the whole window accepts a drop, not just the
    drawn drop zone -- mirrors the Windows drop form)."""

    def initWithFrame_(self, frame):
        self = objc.super(RootView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.registerForDraggedTypes_([NSFilenamesPboardType])
        return self

    def isFlipped(self):
        return False

    def drawRect_(self, dirty):
        _c(BG).setFill()
        NSRectFill(self.bounds())

    def draggingEntered_(self, sender):
        pasteboard = sender.draggingPasteboard()
        if pasteboard.types().containsObject_(NSFilenamesPboardType):
            return NSDragOperationCopy
        return NSDragOperationNone

    def draggingUpdated_(self, sender):
        return self.draggingEntered_(sender)

    def prepareForDragOperation_(self, sender):
        return True

    def performDragOperation_(self, sender):
        pasteboard = sender.draggingPasteboard()
        paths = list(pasteboard.propertyListForType_(NSFilenamesPboardType) or [])
        if not paths:
            return False
        self.window().delegate().appendResults_(scrub_paths(paths))
        return True


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)

        w, h = 600, 560
        rect = NSMakeRect(0, 0, w, h)
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("MetaCLS")
        self.window.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
        self.window.setTitlebarAppearsTransparent_(True)
        self.window.setBackgroundColor_(_c(BG))
        self.window.center()
        self.window.setDelegate_(self)
        self.window.setReleasedWhenClosed_(False)
        self.window.setMinSize_((420, 380))

        content = RootView.alloc().initWithFrame_(rect)
        content.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.window.setContentView_(content)

        header = BrandHeaderView.alloc().initWithFrame_(NSMakeRect(0, h - 70, w, 70))
        header.setAutoresizingMask_(NSViewWidthSizable)
        content.addSubview_(header)

        zone = DropZoneView.alloc().initWithFrame_(NSMakeRect(40, h - 70 - 220, w - 80, 200))
        zone.setAutoresizingMask_(NSViewWidthSizable)
        content.addSubview_(zone)

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(20, 20, w - 40, h - 70 - 220 - 36))
        scroll.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(NSBezelBorder)
        scroll.setDrawsBackground_(True)
        scroll.setBackgroundColor_(_c(PANEL))

        self.log = NSTextView.alloc().initWithFrame_(scroll.contentView().bounds())
        self.log.setAutoresizingMask_(NSViewWidthSizable)
        self.log.setEditable_(False)
        self.log.setDrawsBackground_(True)
        self.log.setBackgroundColor_(_c(PANEL))
        self.log.setTextContainerInset_((6, 6))
        scroll.setDocumentView_(self.log)
        content.addSubview_(scroll)

        placeholder = NSAttributedString.alloc().initWithString_attributes_(
            "Drop a file above to see results here.\n",
            {NSFontAttributeName: NSFont.userFixedPitchFontOfSize_(11), NSForegroundColorAttributeName: _c(DIM)},
        )
        self.log.textStorage().appendAttributedString_(placeholder)

        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def appendResults_(self, lines):
        text = self.log.textStorage()
        mono = NSFont.userFixedPitchFontOfSize_(11)
        for line in lines:
            if line.startswith("ok"):
                color = _c(GREEN_STRONG)
            elif line.startswith("FAIL") or line.startswith("!"):
                color = _c(BAD)
            else:
                color = _c(MUTED)
            attrs = {NSFontAttributeName: mono, NSForegroundColorAttributeName: color}
            run = NSAttributedString.alloc().initWithString_attributes_(line + "\n", attrs)
            text.appendAttributedString_(run)
        self.log.scrollRangeToVisible_((text.length(), 0))

    def windowShouldClose_(self, sender):
        NSApp.terminate_(self)
        return True


def main() -> None:
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
