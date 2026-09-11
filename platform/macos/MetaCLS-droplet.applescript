-- MetaCLS.app — a drag-and-drop droplet.
--
--   * Drop files (or folders) onto the app icon, or onto its Dock icon.
--   * Or double-click the app to pick files with a dialog.
--
-- Every dropped file is scrubbed IN PLACE (originals overwritten with the
-- cleaned version). A notification and a summary dialog report the result.
--
-- Build it into MetaCLS.app with:  platform/macos/build-app.sh
-- (that runs `osacompile -o MetaCLS.app MetaCLS-droplet.applescript`).
--
-- `metacls` must be installed and reachable. GUI apps get a bare PATH,
-- so this script prepends the usual install locations.

property extraPath : "/opt/homebrew/bin:/usr/local/bin:" & (POSIX path of (path to home folder)) & ".local/bin"

on run
	set chosen to choose file with prompt "Pick files to scrub metadata from:" with multiple selections allowed
	processFiles(chosen)
end run

on open droppedItems
	processFiles(droppedItems)
end open

on processFiles(theItems)
	set metacls to findMetacls()
	if metacls is "" then
		display dialog "Couldn't find the `metacls` command." & return & return & ¬
			"Install it with:  pip install metacls  (or pipx install metacls)" ¬
			buttons {"OK"} default button "OK" with icon stop
		return
	end if

	set okCount to 0
	set failCount to 0
	set failNames to {}

	repeat with anItem in theItems
		set p to quoted form of (POSIX path of anItem)
		set cmd to metacls & " clean " & p & " --in-place --yes --no-json-report --no-html-report"
		try
			do shell script cmd
			set okCount to okCount + 1
		on error
			set failCount to failCount + 1
			set end of failNames to (name of (info for anItem))
		end try
	end repeat

	set msg to "Scrubbed " & okCount & " file(s)"
	if failCount > 0 then set msg to msg & ", " & failCount & " failed"
	try
		display notification msg with title "MetaCLS"
	end try
	if failCount > 0 then
		display dialog msg & return & return & "Failed: " & (my joinList(failNames, ", ")) ¬
			buttons {"OK"} default button "OK" with icon caution
	end if
end processFiles

on findMetacls()
	try
		return do shell script "PATH=" & extraPath & ":$PATH; command -v metacls"
	on error
		return ""
	end try
end findMetacls

on joinList(theList, sep)
	set {oldTID, AppleScript's text item delimiters} to {AppleScript's text item delimiters, sep}
	set s to theList as text
	set AppleScript's text item delimiters to oldTID
	return s
end joinList
