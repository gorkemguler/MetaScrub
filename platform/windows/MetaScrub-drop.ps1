<#
MetaScrub-drop.ps1 — a tiny drag-and-drop window.

    powershell -ExecutionPolicy Bypass -File MetaScrub-drop.ps1
    powershell -ExecutionPolicy Bypass -File MetaScrub-drop.ps1 file1.pdf file2.docx

Drop files onto the window (or pass them as arguments) and they're
scrubbed IN PLACE with `metascrub clean --in-place`. Results show in the
list; nothing leaves your machine.

`metascrub` must be on PATH (`pip install metascrub` / `pipx install
metascrub`). `install-sendto.ps1` wires this into the Send-to menu.
#>
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Files)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Resolve-Metascrub {
    $c = Get-Command metascrub.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $c = Get-Command metascrub -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}

$script:metascrub = Resolve-Metascrub

$form = New-Object System.Windows.Forms.Form
$form.Text = "MetaScrub — drop files to scrub metadata"
$form.Size = New-Object System.Drawing.Size(560, 420)
$form.StartPosition = "CenterScreen"
$form.AllowDrop = $true

$hint = New-Object System.Windows.Forms.Label
$hint.Text = "Drop PDF / Office / image / SVG files here.`r`nThey are scrubbed in place."
$hint.Dock = "Top"
$hint.Height = 60
$hint.TextAlign = "MiddleCenter"
$hint.Font = New-Object System.Drawing.Font("Segoe UI", 11)
$form.Controls.Add($hint)

$list = New-Object System.Windows.Forms.ListBox
$list.Dock = "Fill"
$list.Font = New-Object System.Drawing.Font("Consolas", 9)
$form.Controls.Add($list)
$list.BringToFront()

function Scrub-Files([string[]] $paths) {
    if (-not $script:metascrub) {
        $list.Items.Add("! metascrub not found on PATH — pip install metascrub") | Out-Null
        return
    }
    $ok = 0; $fail = 0
    foreach ($p in $paths) {
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { continue }
        $args = @("clean", $p, "--in-place", "--yes", "--no-json-report", "--no-html-report")
        & $script:metascrub @args 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ok++
            $list.Items.Add("ok    $([System.IO.Path]::GetFileName($p))") | Out-Null
        } else {
            $fail++
            $list.Items.Add("FAIL  $([System.IO.Path]::GetFileName($p))  (exit $LASTEXITCODE)") | Out-Null
        }
        $list.TopIndex = $list.Items.Count - 1
    }
    $list.Items.Add("-- scrubbed $ok, failed $fail --") | Out-Null
}

$form.Add_DragEnter({
    if ($_.Data.GetDataPresent([System.Windows.Forms.DataFormats]::FileDrop)) {
        $_.Effect = [System.Windows.Forms.DragDropEffects]::Copy
    }
})
$form.Add_DragDrop({
    $dropped = $_.Data.GetData([System.Windows.Forms.DataFormats]::FileDrop)
    Scrub-Files $dropped
})

if ($Files -and $Files.Count -gt 0) {
    $form.Add_Shown({ Scrub-Files $Files })
}

[void] $form.ShowDialog()
