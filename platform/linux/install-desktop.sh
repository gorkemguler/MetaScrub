#!/bin/bash
# Install (or remove) the MetaScrub desktop launcher + "Open With" MIME
# handler for the current user. No root.
#
#   platform/linux/install-desktop.sh            # install
#   platform/linux/install-desktop.sh --uninstall
#
# After install: drag files onto "MetaScrub" in your app menu, or
# right-click a file -> Open With Other Application -> MetaScrub. Files
# are scrubbed in place. `metascrub` must be on PATH.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
bin_dir="$HOME/.local/bin"
app_dir="$HOME/.local/share/applications"
desktop="$app_dir/metascrub.desktop"
script="$bin_dir/metascrub-drop.sh"

if [ "${1:-}" = "--uninstall" ]; then
	rm -f "$desktop" "$script"
	command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$app_dir" || true
	echo "Removed metascrub.desktop and metascrub-drop.sh."
	exit 0
fi

mkdir -p "$bin_dir" "$app_dir"
install -m755 "$here/metascrub-drop.sh" "$script"
install -m644 "$here/metascrub.desktop" "$desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$app_dir" || true

case ":$PATH:" in
	*":$bin_dir:"*) ;;
	*) echo "note: $bin_dir is not on PATH — add it so the launcher can find metascrub-drop.sh" ;;
esac

echo "Installed. Find 'MetaScrub' in your applications menu, or use"
echo "right-click -> Open With -> MetaScrub. Files are scrubbed in place."
