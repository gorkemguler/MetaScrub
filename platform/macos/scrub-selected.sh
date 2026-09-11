#!/bin/bash
# Scrub the files passed as arguments, in place, and show a notification.
#
# Wire this up as a Finder Quick Action:
#   1. Automator -> New -> Quick Action
#   2. "Workflow receives current" = files or folders, in "Finder"
#   3. Add a "Run Shell Script" action, "Pass input: as arguments"
#   4. Paste:  exec /full/path/to/scrub-selected.sh "$@"
#   5. Save as "Scrub metadata"  ->  it appears in Finder's right-click menu
#
# `install-quick-action.sh` in this folder does steps 1-5 for you.

set -u
METACLS="${METACLS:-metacls}"
command -v "$METACLS" >/dev/null || METACLS="$HOME/.local/bin/metacls"

ok=0 fail=0
for f in "$@"; do
  if "$METACLS" clean "$f" --in-place --yes --no-json-report --no-html-report >/dev/null 2>&1; then
    ok=$((ok + 1))
  else
    fail=$((fail + 1))
  fi
done

msg="Scrubbed $ok file(s)"
[ "$fail" -gt 0 ] && msg="$msg, $fail failed"
osascript -e "display notification \"$msg\" with title \"MetaCLS\"" 2>/dev/null || true
