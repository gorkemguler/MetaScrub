#!/bin/bash
# MetaCLS drop / "Open with" handler for the Linux desktop.
#
#   metacls-drop.sh [FILE ...]
#
# Invoked by metacls.desktop (drag files onto its launcher, or
# right-click -> Open With -> MetaCLS). With no arguments it opens a
# file picker (zenity). Every file is scrubbed IN PLACE; the result is
# reported via zenity if present, else notify-send, else stdout.
set -u

METACLS="${METACLS:-metacls}"
command -v "$METACLS" >/dev/null 2>&1 || METACLS="$HOME/.local/bin/metacls"

have_zenity() { command -v zenity >/dev/null 2>&1; }

report() {
	if have_zenity; then
		zenity --info --title="MetaCLS" --text="$1" 2>/dev/null || true
	elif command -v notify-send >/dev/null 2>&1; then
		notify-send "MetaCLS" "$(printf '%b' "$1")"
	else
		printf '%b\n' "$1"
	fi
}

if [ "$#" -eq 0 ] && have_zenity; then
	mapfile -t picked < <(zenity --file-selection --multiple --separator=$'\n' \
		--title="MetaCLS — pick files to scrub" 2>/dev/null) || exit 0
	set -- "${picked[@]}"
fi
[ "$#" -eq 0 ] && exit 0

if ! command -v "$METACLS" >/dev/null 2>&1; then
	report "metacls is not installed or not on PATH.\nInstall it with:  pip install metacls"
	exit 1
fi

ok=0
fail=0
failed=""
for f in "$@"; do
	[ -f "$f" ] || continue
	if "$METACLS" clean "$f" --in-place --yes --no-json-report --no-html-report >/dev/null 2>&1; then
		ok=$((ok + 1))
	else
		fail=$((fail + 1))
		failed="${failed}  $(basename "$f")\n"
	fi
done

msg="Scrubbed $ok file(s)"
[ "$fail" -gt 0 ] && msg="$msg, $fail failed:\n$failed"
report "$msg"
[ "$fail" -eq 0 ]
