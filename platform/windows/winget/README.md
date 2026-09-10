# winget manifest (template)

A [winget](https://learn.microsoft.com/windows/package-manager/) manifest
for `GorkemGuler.MetaScrub`, ready to submit to
[`microsoft/winget-pkgs`](https://github.com/microsoft/winget-pkgs) once a
release ships a Windows artifact.

It is a **template**: the `InstallerUrl` and `InstallerSha256` in
`GorkemGuler.MetaScrub.installer.yaml` are placeholders. To finish it:

1. Publish a portable build as a release asset, e.g.
   `metascrub-<version>-windows-x64.zip` containing `metascrub.exe`
   (PyInstaller / `pip install --target` + a launcher, etc.).
2. Fill in `InstallerUrl` with that asset's URL and `InstallerSha256`
   with `(Get-FileHash file.zip -Algorithm SHA256).Hash`.
3. Bump `PackageVersion` in all three files to match.
4. Validate and submit:

   ```powershell
   winget validate --manifest platform\windows\winget
   winget install --manifest platform\windows\winget   # local test
   ```

Until then, install MetaScrub with `pip install metascrub` (or
`pipx install metascrub`) and use `install-context-menu.ps1` /
`install-sendto.ps1` for the shell integration.
