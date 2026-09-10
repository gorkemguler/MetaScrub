<#
Adds / removes a "MetaScrub" entry in the Windows **Send to** menu
(right-click a file → Send to → MetaScrub). Selecting it opens the
drop window (MetaScrub-drop.ps1) pre-loaded with the selected files.

    powershell -ExecutionPolicy Bypass -File install-sendto.ps1
    powershell -ExecutionPolicy Bypass -File install-sendto.ps1 -Uninstall

Current user only, no admin. `metascrub` must be on PATH.
#>
param([switch]$Uninstall)

$sendTo = [Environment]::GetFolderPath('SendTo')
$lnkPath = Join-Path $sendTo 'MetaScrub.lnk'
$dropScript = Join-Path $PSScriptRoot 'MetaScrub-drop.ps1'

if ($Uninstall) {
    Remove-Item -LiteralPath $lnkPath -Force -ErrorAction SilentlyContinue
    Write-Host "Removed the MetaScrub Send-to entry."
    return
}

if (-not (Test-Path -LiteralPath $dropScript)) {
    Write-Error "MetaScrub-drop.ps1 not found next to this script."
    exit 1
}

$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $pwsh) { $pwsh = Join-Path $PSHOME 'powershell.exe' }

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $pwsh
$lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$dropScript`""
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.IconLocation = "shell32.dll,77"
$lnk.Description = "Scrub metadata with MetaScrub"
$lnk.Save()

Write-Host "Added 'MetaScrub' to the Send-to menu -> $lnkPath"
Write-Host "Right-click file(s) -> Send to -> MetaScrub."
