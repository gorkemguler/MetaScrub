#!/bin/bash
# Build MetaCLS.app — a no-Xcode drag-and-drop droplet — from
# MetaCLS-droplet.applescript, using the `osacompile` tool that ships
# with macOS.
#
#   platform/macos/build-app.sh [DEST_DIR]
#
# DEST_DIR defaults to /Applications if writable, else ~/Applications.
# Drop files onto the built app (Finder icon or Dock) to scrub them in
# place; double-click it to pick files with a dialog.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
src="$here/MetaCLS-droplet.applescript"

dest="${1:-}"
if [ -z "$dest" ]; then
	if [ -w /Applications ]; then dest=/Applications; else dest="$HOME/Applications"; fi
fi
mkdir -p "$dest"
app="$dest/MetaCLS.app"

rm -rf "$app"
osacompile -o "$app" "$src"

# Make it a proper droplet: mark it as accepting every file type, give it
# a stable bundle id, and hide it from the Dock's "recent apps" churn.
plist="$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.gorkemguler.metacls" "$plist" 2>/dev/null || \
	/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.gorkemguler.metacls" "$plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleName string MetaCLS" "$plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDocumentTypes array" "$plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDocumentTypes:0 dict" "$plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDocumentTypes:0:CFBundleTypeRole string Editor" "$plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes array" "$plist" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :CFBundleDocumentTypes:0:LSItemContentTypes:0 string public.item" "$plist" 2>/dev/null || true

# Refresh Launch Services so the app is picked up immediately.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
	-f "$app" 2>/dev/null || true

echo "Built $app"
echo "Drag files onto it (Finder or Dock) to scrub them in place."
