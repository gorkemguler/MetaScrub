# Platform integration

Right-click / drop-folder integration for MetaScrub. `metascrub` must be
installed and on `PATH` (`pip install metascrub`, `pipx install metascrub`,
or a venv you add to `PATH`).

## macOS — Finder Quick Action

```bash
platform/macos/install-quick-action.sh
```

Builds a **Scrub metadata** Quick Action in `~/Library/Services/`. Right-click
one or more files in Finder → *Quick Actions* → *Scrub metadata*. They're
scrubbed **in place**. Remove it by deleting
`~/Library/Services/Scrub metadata.workflow`.

`scrub-selected.sh` is the script it calls — you can also add it by hand
in Automator (see the comment at the top of the file).

## Windows — Explorer right-click

```powershell
powershell -ExecutionPolicy Bypass -File platform\windows\install-context-menu.ps1
```

Adds *Scrub metadata with MetaScrub* to the right-click menu for PDF /
Office / image / SVG files (current user, no admin). Undo with the same
script plus `-Uninstall`.

## Linux — file-manager script

```bash
mkdir -p ~/.local/share/nautilus/scripts
install -m755 platform/linux/nautilus-scrub-metadata.sh \
  ~/.local/share/nautilus/scripts/"Scrub metadata"
```

Right-click → *Scripts* → *Scrub metadata* (Nautilus/Files; see the script
header for Nemo/Caja paths).

## Linux — drop-folder daemon

`platform/linux/metascrub-watch@.service` is a systemd template unit for
`metascrub watch` — see the [README](../README.md#watch--keep-a-drop-folder-scrubbed).
