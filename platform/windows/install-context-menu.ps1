<#
Adds a "Scrub metadata with MetaCLS" entry to the right-click menu for
PDF / Office / image / SVG files, for the current user (HKCU — no admin).

    powershell -ExecutionPolicy Bypass -File install-context-menu.ps1
    powershell -ExecutionPolicy Bypass -File install-context-menu.ps1 -Uninstall

`metacls` must be on PATH (e.g. `pip install metacls` or pipx).
#>
param([switch]$Uninstall)

$exts = ".pdf",".docx",".xlsx",".pptx",".odt",".ods",".odp",".doc",".xls",".ppt",
        ".svg",".jpg",".jpeg",".png",".tif",".tiff",".heic",".webp"
$verb = "MetaCLS.Scrub"
$label = "Scrub metadata with MetaCLS"

# pythonw so no console window flashes; fall back to metacls.exe on PATH.
$mscrub = (Get-Command metacls.exe -ErrorAction SilentlyContinue).Source
if (-not $mscrub) { $mscrub = "metacls" }
$cmd = "`"$mscrub`" clean `"%1`" --in-place --yes --no-json-report --no-html-report"

foreach ($ext in $exts) {
    $base = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\$verb"
    if ($Uninstall) {
        Remove-Item -Path $base -Recurse -Force -ErrorAction SilentlyContinue
        continue
    }
    New-Item -Path "$base\command" -Force | Out-Null
    Set-ItemProperty -Path $base -Name "(default)" -Value $label
    Set-ItemProperty -Path $base -Name "Icon" -Value "shell32.dll,77"
    Set-ItemProperty -Path "$base\command" -Name "(default)" -Value $cmd
}

if ($Uninstall) { Write-Host "Removed the MetaCLS context-menu entry." }
else { Write-Host "Added '$label' to the right-click menu for: $($exts -join ' ')" }
