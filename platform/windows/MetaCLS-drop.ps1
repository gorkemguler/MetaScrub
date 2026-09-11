<#
MetaCLS-drop.ps1 -- a persistent drag-and-drop window. Styled to match
the project's dark/green branding (see assets/banner.svg,
assets/desktop-apps.svg) -- the same look as
platform/macos/metacls_drop.py and platform/linux/metacls_drop_gtk.py.

    powershell -ExecutionPolicy Bypass -File MetaCLS-drop.ps1
    powershell -ExecutionPolicy Bypass -File MetaCLS-drop.ps1 file1.pdf file2.docx

Drop files onto the window (or pass them as arguments) and they're
scrubbed IN PLACE with `metacls clean --in-place`. Results show in the
list; nothing leaves your machine.

`metacls` must be on PATH (`pip install metacls` / `pipx install
metacls`). `install-sendto.ps1` wires this into the Send-to menu.
#>
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $Files)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# The brand palette from assets/banner.svg / assets/desktop-apps.svg.
$Bg          = [System.Drawing.Color]::FromArgb(0x0C, 0x11, 0x10)
$Panel       = [System.Drawing.Color]::FromArgb(0x13, 0x20, 0x1C)
$Border      = [System.Drawing.Color]::FromArgb(0x22, 0x33, 0x2E)
$Green       = [System.Drawing.Color]::FromArgb(0x2D, 0xD4, 0xA7)
$GreenStrong = [System.Drawing.Color]::FromArgb(0x34, 0xD3, 0x99)
$Ink         = [System.Drawing.Color]::FromArgb(0xE9, 0xEF, 0xED)
$Muted       = [System.Drawing.Color]::FromArgb(0x93, 0xA5, 0xA0)
$Dim         = [System.Drawing.Color]::FromArgb(0x6F, 0x84, 0x80)
$Bad         = [System.Drawing.Color]::FromArgb(0xF8, 0x71, 0x71)

# Dark title bar (Windows 10 1809+ / 11); a no-op, harmlessly, on older
# builds since DwmSetWindowAttribute just returns a non-zero HRESULT.
Add-Type -Name Dwm -Namespace MetaCLS -MemberDefinition @"
[System.Runtime.InteropServices.DllImport("dwmapi.dll")]
public static extern int DwmSetWindowAttribute(System.IntPtr hwnd, int attr, ref int value, int size);
"@

function Resolve-Metacls {
    $c = Get-Command metacls.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $c = Get-Command metacls -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}

$script:metacls = Resolve-Metacls

$form = New-Object System.Windows.Forms.Form
$form.Text = "MetaCLS"
$form.Size = New-Object System.Drawing.Size(600, 620)
$form.StartPosition = "CenterScreen"
$form.AllowDrop = $true
$form.BackColor = $Bg
$form.Padding = New-Object System.Windows.Forms.Padding(20)

$form.Add_Shown({
    [int]$dark = 1
    # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (19 on older 1809-era builds).
    [MetaCLS.Dwm]::DwmSetWindowAttribute($form.Handle, 20, [ref]$dark, 4) | Out-Null
    [MetaCLS.Dwm]::DwmSetWindowAttribute($form.Handle, 19, [ref]$dark, 4) | Out-Null
})

# ---- brand header: "meta" + "cls" wordmark + tagline ----------------
$header = New-Object System.Windows.Forms.Panel
$header.Dock = "Top"
$header.Height = 64
$header.BackColor = $Bg

$wordmark = New-Object System.Windows.Forms.Label
$wordmark.AutoSize = $true
$wordmark.Font = New-Object System.Drawing.Font("Segoe UI", 18, [System.Drawing.FontStyle]::Bold)
$wordmark.BackColor = $Bg
$wordmark.Text = "meta"
$wordmark.ForeColor = $Ink

$wordmarkCls = New-Object System.Windows.Forms.Label
$wordmarkCls.AutoSize = $true
$wordmarkCls.Font = $wordmark.Font
$wordmarkCls.BackColor = $Bg
$wordmarkCls.Text = "cls"
$wordmarkCls.ForeColor = $GreenStrong

$tagline = New-Object System.Windows.Forms.Label
$tagline.AutoSize = $true
$tagline.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$tagline.BackColor = $Bg
$tagline.ForeColor = $Dim
$tagline.Text = "strip the metadata . keep the document"

$header.Controls.AddRange(@($wordmark, $wordmarkCls, $tagline))
$updateHeaderLayout = {
    $totalW = $wordmark.PreferredWidth + $wordmarkCls.PreferredWidth
    $x = [Math]::Max(0, ($header.Width - $totalW) / 2)
    $wordmark.Location = New-Object System.Drawing.Point($x, 6)
    $wordmarkCls.Location = New-Object System.Drawing.Point(($x + $wordmark.PreferredWidth), 6)
    $tx = [Math]::Max(0, ($header.Width - $tagline.PreferredWidth) / 2)
    $tagline.Location = New-Object System.Drawing.Point($tx, 38)
}
$header.Add_Resize($updateHeaderLayout)
$form.Controls.Add($header)
# Resize fires on layout, but run it once now too so the wordmark is
# centered immediately instead of only after the user resizes the window.
& $updateHeaderLayout

# ---- drop zone: dashed rounded rect + doc icon + hint text ----------
$zone = New-Object System.Windows.Forms.Panel
$zone.Dock = "Top"
$zone.Height = 220
$zone.BackColor = $Bg
$zone.Margin = New-Object System.Windows.Forms.Padding(0, 12, 0, 12)

$zone.Add_Paint({
    param($s, $e)
    $g = $e.Graphics
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $rect = New-Object System.Drawing.Rectangle(20, 4, ($zone.Width - 44), ($zone.Height - 12))

    $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(140, $Green), 2)
    $pen.DashStyle = [System.Drawing.Drawing2D.DashStyle]::Custom
    $pen.DashPattern = @(6, 5)
    $radius = 16
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2
    $path.AddArc($rect.X, $rect.Y, $d, $d, 180, 90)
    $path.AddArc(($rect.Right - $d), $rect.Y, $d, $d, 270, 90)
    $path.AddArc(($rect.Right - $d), ($rect.Bottom - $d), $d, $d, 0, 90)
    $path.AddArc($rect.X, ($rect.Bottom - $d), $d, $d, 90, 90)
    $path.CloseFigure()
    $g.DrawPath($pen, $path)

    $cx = $rect.X + $rect.Width / 2
    $cy = $rect.Y + $rect.Height / 2 - 20

    $lineWidths = @(46, 36, 24)
    $lineAlphas = @(230, 150, 90)
    for ($i = 0; $i -lt 3; $i++) {
        $lp = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb($lineAlphas[$i], $Green), 6)
        $lp.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $lp.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $y = $cy - 14 + ($i * 13)
        $g.DrawLine($lp, ($cx - 55), $y, ($cx - 55 + $lineWidths[$i]), $y)
    }

    $docRect = New-Object System.Drawing.Rectangle(($cx + 6), ($cy - 24), 34, 46)
    $g.FillRectangle((New-Object System.Drawing.SolidBrush($Bg)), $docRect)
    $g.DrawRectangle((New-Object System.Drawing.Pen($GreenStrong, 2)), $docRect)
    $fold = @(
        (New-Object System.Drawing.Point(($docRect.Right - 11), $docRect.Y)),
        (New-Object System.Drawing.Point($docRect.Right, ($docRect.Y + 11))),
        (New-Object System.Drawing.Point(($docRect.Right - 11), ($docRect.Y + 11)))
    )
    $g.FillPolygon((New-Object System.Drawing.SolidBrush($GreenStrong)), $fold)

    $hintFont = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $hintFmt = New-Object System.Drawing.StringFormat
    $hintFmt.Alignment = [System.Drawing.StringAlignment]::Center
    $g.DrawString("Drag & drop to scrub", $hintFont, (New-Object System.Drawing.SolidBrush($Ink)),
        (New-Object System.Drawing.RectangleF($rect.X, ($rect.Bottom - 48), $rect.Width, 22)), $hintFmt)

    $subFont = New-Object System.Drawing.Font("Segoe UI", 8.5)
    $g.DrawString("Scrubbed in place - nothing else leaves this window.", $subFont,
        (New-Object System.Drawing.SolidBrush($Dim)),
        (New-Object System.Drawing.RectangleF($rect.X, ($rect.Bottom - 26), $rect.Width, 18)), $hintFmt)
})
$form.Controls.Add($zone)

# ---- results log ------------------------------------------------------
$list = New-Object System.Windows.Forms.ListBox
$list.Dock = "Fill"
$list.Font = New-Object System.Drawing.Font("Consolas", 9.5)
$list.BackColor = $Panel
$list.ForeColor = $Muted
$list.BorderStyle = "FixedSingle"
$list.DrawMode = "OwnerDrawFixed"
$list.ItemHeight = 18
$list.Items.Add("Drop a file above to see results here.") | Out-Null

$list.Add_DrawItem({
    param($s, $e)
    $e.Graphics.FillRectangle((New-Object System.Drawing.SolidBrush($Panel)), $e.Bounds)
    if ($e.Index -lt 0) { return }
    $text = $list.Items[$e.Index].ToString()
    $color = $Muted
    if ($text.StartsWith("ok")) { $color = $GreenStrong }
    elseif ($text.StartsWith("FAIL") -or $text.StartsWith("!")) { $color = $Bad }
    $brush = New-Object System.Drawing.SolidBrush($color)
    $e.Graphics.DrawString($text, $list.Font, $brush, $e.Bounds.X + 4, $e.Bounds.Y + 1)
})

$form.Controls.Add($list)
$list.BringToFront()

function Scrub-Files([string[]] $paths) {
    if (-not $script:metacls) {
        $list.Items.Add("! metacls not found on PATH - pip install metacls") | Out-Null
        return
    }
    $ok = 0; $fail = 0
    foreach ($p in $paths) {
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { continue }
        $args = @("clean", $p, "--in-place", "--yes", "--no-json-report", "--no-html-report")
        & $script:metacls @args 2>&1 | Out-Null
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
