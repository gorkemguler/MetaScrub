#!/usr/bin/env python3
"""MetaCLS Drop — a persistent drag-and-drop window, the macOS
counterpart to platform/windows/MetaCLS-drop.ps1.

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
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSColor,
    NSDragOperationCopy,
    NSDragOperationNone,
    NSFilenamesPboardType,
    NSFont,
    NSMakeRect,
    NSScrollView,
    NSTextField,
    NSTextView,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
from PyObjCTools import AppHelper


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


class DropView(NSView):
    """The window's whole content view: accepts a Finder file drag and
    forwards the dropped paths to the app delegate's log."""

    def initWithFrame_(self, frame):
        self = objc.super(DropView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.registerForDraggedTypes_([NSFilenamesPboardType])
        return self

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

        rect = NSMakeRect(0, 0, 560, 420)
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("MetaCLS — drop files to scrub metadata")
        self.window.center()
        self.window.setDelegate_(self)
        self.window.setReleasedWhenClosed_(False)

        content = DropView.alloc().initWithFrame_(rect)
        self.window.setContentView_(content)

        hint = NSTextField.alloc().initWithFrame_(NSMakeRect(16, 360, 528, 44))
        hint.setStringValue_(
            "Drop PDF / Office / image / SVG files here.\nThey are scrubbed in place."
        )
        hint.setEditable_(False)
        hint.setBezeled_(False)
        hint.setDrawsBackground_(False)
        hint.setAlignment_(1)  # NSTextAlignmentCenter
        hint.setFont_(NSFont.systemFontOfSize_(13))
        content.addSubview_(hint)

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(16, 16, 528, 332))
        scroll.setHasVerticalScroller_(True)
        scroll.setBorderType_(1)  # NSBezelBorder
        scroll.setAutoresizingMask_(1 << 1 | 1 << 4)  # width + height sizable

        self.log = NSTextView.alloc().initWithFrame_(scroll.contentView().bounds())
        self.log.setEditable_(False)
        self.log.setFont_(NSFont.userFixedPitchFontOfSize_(11))
        self.log.setBackgroundColor_(NSColor.textBackgroundColor())
        scroll.setDocumentView_(self.log)
        content.addSubview_(scroll)

        self.window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def appendResults_(self, lines):
        text = self.log.textStorage()
        for line in lines:
            text.mutableString().appendString_(line + "\n")
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
