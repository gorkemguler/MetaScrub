#!/bin/bash
# Nautilus / Files right-click script.
#
#   mkdir -p ~/.local/share/nautilus/scripts
#   cp nautilus-scrub-metadata.sh "~/.local/share/nautilus/scripts/Scrub metadata"
#   chmod +x "~/.local/share/nautilus/scripts/Scrub metadata"
#
# Then: right-click files → Scripts → Scrub metadata.
# (Nemo: ~/.local/share/nemo/scripts/ ; Caja: ~/.config/caja/scripts/)

IFS=$'\n'
ok=0 fail=0
for f in $NAUTILUS_SCRIPT_SELECTED_FILE_PATHS; do
    [ -f "$f" ] || continue
    if metacls clean "$f" --in-place --yes --no-json-report --no-html-report >/dev/null 2>&1; then
        ok=$((ok + 1))
    else
        fail=$((fail + 1))
    fi
done

if command -v notify-send >/dev/null; then
    msg="Scrubbed $ok file(s)"
    [ "$fail" -gt 0 ] && msg="$msg, $fail failed"
    notify-send "MetaCLS" "$msg"
fi
