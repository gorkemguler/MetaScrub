#!/bin/bash
# Build "MetaCLS Drop.app" — a persistent drag-and-drop window, the
# macOS counterpart to platform/windows/MetaCLS-drop.ps1. Unlike
# MetaCLS.app (build-app.sh), which is a zero-dependency AppleScript
# droplet, this opens a real window you drop files onto and leave open;
# it needs PyObjC, so this script sets that up in its own venv (not
# your global Python) and wraps metacls_drop.py into the app bundle.
#
#   platform/macos/build-drop-app.sh [DEST_DIR]
#
# DEST_DIR defaults to /Applications if writable, else ~/Applications.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
script="$here/metacls_drop.py"

dest="${1:-}"
if [ -z "$dest" ]; then
	if [ -w /Applications ]; then dest=/Applications; else dest="$HOME/Applications"; fi
fi
mkdir -p "$dest"
app="$dest/MetaCLS Drop.app"

venv_dir="$HOME/Library/Application Support/MetaCLS/drop-venv"
if [ ! -x "$venv_dir/bin/python3" ]; then
	echo "Setting up the drop window's Python environment (one-time, ~30s)..."
	python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/pip" install --quiet --upgrade pip pyobjc-framework-Cocoa

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$script" "$app/Contents/Resources/metacls_drop.py"

cat > "$app/Contents/MacOS/MetaCLS Drop" <<LAUNCHER
#!/bin/bash
exec "$venv_dir/bin/python3" "\$(dirname "\$0")/../Resources/metacls_drop.py"
LAUNCHER
chmod +x "$app/Contents/MacOS/MetaCLS Drop"

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>MetaCLS Drop</string>
  <key>CFBundleDisplayName</key><string>MetaCLS Drop</string>
  <key>CFBundleIdentifier</key><string>com.gorkemguler.metacls.drop</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>MetaCLS Drop</string>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
</dict></plist>
PLIST

/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister \
	-f "$app" 2>/dev/null || true

echo "Built '$app'"
echo "Open it, then drop files onto the window to scrub them in place."
