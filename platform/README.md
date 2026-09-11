# Platform integration

Right-click, drop-target and drop-folder integration for MetaCLS.
`metacls` must be installed and on `PATH` (`pip install metacls`,
`pipx install metacls`, or a venv you add to `PATH`). Everything here
scrubs **in place**: the originals are overwritten with the cleaned
version.

## macOS

### Drop app: `MetaCLS.app`

```bash
platform/macos/build-app.sh            # -> /Applications/MetaCLS.app
```

Builds a self-contained droplet with `osacompile` (no Xcode). Drag files
onto its Finder icon or its Dock icon; double-click it to pick files with
a dialog. A notification reports the result. Delete the `.app` to remove
it. Source: `MetaCLS-droplet.applescript`.

### Finder Quick Action

```bash
platform/macos/install-quick-action.sh
```

Adds a **Scrub metadata** Quick Action in `~/Library/Services/`.
Right-click one or more files in Finder → *Quick Actions* → *Scrub
metadata*. Remove it by deleting `~/Library/Services/Scrub metadata.workflow`.
`scrub-selected.sh` is the script it calls.

## Windows

### Drop window: `MetaCLS-drop.ps1`

```powershell
powershell -ExecutionPolicy Bypass -File platform\windows\MetaCLS-drop.ps1
```

A small WinForms window: drop files onto it (or pass them as arguments)
and they're scrubbed, with a per-file result list.

### Send-to menu

```powershell
powershell -ExecutionPolicy Bypass -File platform\windows\install-sendto.ps1
powershell -ExecutionPolicy Bypass -File platform\windows\install-sendto.ps1 -Uninstall
```

Adds **MetaCLS** to the right-click *Send to* menu, opening the drop
window pre-loaded with the selected files.

### Explorer right-click

```powershell
powershell -ExecutionPolicy Bypass -File platform\windows\install-context-menu.ps1
powershell -ExecutionPolicy Bypass -File platform\windows\install-context-menu.ps1 -Uninstall
```

Adds *Scrub metadata with MetaCLS* to the right-click menu for PDF /
Office / image / SVG files (current user, no admin).

### winget

`platform/windows/winget/` holds a manifest for `GorkemGuler.MetaCLS`,
ready to submit to `winget-pkgs` once a release ships a Windows artifact.
See the README there.

## Linux

### Desktop launcher + "Open With" handler

```bash
platform/linux/install-desktop.sh              # install
platform/linux/install-desktop.sh --uninstall
```

Installs `metacls.desktop` (+ `metacls-drop.sh` into `~/.local/bin`).
Drag files onto **MetaCLS** in your applications menu, or right-click a
file → *Open With* → *MetaCLS*. With no files it opens a `zenity` file
picker. Results go to `zenity` / `notify-send` / stdout.

### File-manager script (Nautilus / Nemo / Caja)

```bash
mkdir -p ~/.local/share/nautilus/scripts
install -m755 platform/linux/nautilus-scrub-metadata.sh \
  ~/.local/share/nautilus/scripts/"Scrub metadata"
```

Right-click → *Scripts* → *Scrub metadata* (see the script header for
Nemo/Caja paths).

### Drop-folder daemon

`platform/linux/metacls-watch@.service` is a systemd template unit for
`metacls watch`: see the
[README](https://github.com/gorkemguler/MetaCLS/blob/main/README.md#watch-keep-a-drop-folder-scrubbed).
