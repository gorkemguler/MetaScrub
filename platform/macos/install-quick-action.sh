#!/bin/bash
# Build a "Scrub metadata" Finder Quick Action and install it for the
# current user. Undo by deleting ~/Library/Services/Scrub metadata.workflow
# (or via System Settings -> Keyboard -> Keyboard Shortcuts -> Services).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
name="Scrub metadata"
dst="$HOME/Library/Services/${name}.workflow"
script="$here/scrub-selected.sh"

chmod +x "$script"
mkdir -p "$dst/Contents"

cat > "$dst/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>NSServices</key><array><dict>
    <key>NSMenuItem</key><dict><key>default</key><string>${name}</string></dict>
    <key>NSMessage</key><string>runWorkflowAsService</string>
    <key>NSSendFileTypes</key><array><string>public.item</string></array>
  </dict></array>
</dict></plist>
PLIST

cat > "$dst/Contents/document.wflow" <<WFLOW
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>AMApplicationBuild</key><string>0</string>
  <key>actions</key><array><dict><key>action</key><dict>
    <key>AMActionVersion</key><string>2.0.3</string>
    <key>ActionBundlePath</key><string>/System/Library/Automator/Run Shell Script.action</string>
    <key>ActionName</key><string>Run Shell Script</string>
    <key>ActionParameters</key><dict>
      <key>COMMAND_STRING</key><string>exec "${script}" "\$@"</string>
      <key>inputMethod</key><integer>1</integer>
      <key>shell</key><string>/bin/bash</string>
    </dict>
    <key>BundleIdentifier</key><string>com.apple.RunShellScript</string>
  </dict></dict></array>
  <key>workflowMetaData</key><dict>
    <key>serviceInputTypeIdentifier</key><string>com.apple.Automator.fileSystemObject</string>
    <key>serviceApplicationBundleID</key><string>com.apple.finder</string>
    <key>applicationBundleIDsByPath</key><dict/>
    <key>inputTypeIdentifier</key><string>com.apple.Automator.fileSystemObject</string>
    <key>presentationMode</key><integer>2</integer>
  </dict>
</dict></plist>
WFLOW

/System/Library/CoreServices/pbs -flush 2>/dev/null || true
echo "Installed '${name}' — right-click files in Finder → Quick Actions → ${name}."
