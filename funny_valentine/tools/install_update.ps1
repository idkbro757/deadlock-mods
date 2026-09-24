# Funny Valentine update: his revolver + D4C in the Hotel.
# Copies the files in the "addon" folder next to this script into your CSDK12 funny_valentine addon,
# stamped with the current time so the compilers pick them up. Existing files with the same name are
# replaced; nothing else in the addon is touched.
# Usage: double-click "Install FV update.bat" (or drag your CSDK12 folder onto it).
#        Run "Check FV update.bat" after compiling to see what's built and what's still missing.
param([string]$CsdkPath = "", [switch]$Check)
$ErrorActionPreference = "Stop"
function Say($m, $c = "Gray") { Write-Host $m -ForegroundColor $c }

function Find-Addon {
    $tail = "funny_valentine\models\heroes_wip\doorman_v2\doorman.vmdl"
    $home_ = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
    # (folder, how deep to look) - specific spots first, whole drives last
    $places = @()
    if ($CsdkPath) { $places += ,@($CsdkPath, 3) }
    foreach ($p in "C:\CSDK12", "D:\CSDK12", "C:\Reduced_CSDK_12", "D:\Reduced_CSDK_12") { $places += ,@($p, 2) }
    foreach ($f in "Desktop", "Downloads", "Documents", "OneDrive") { $places += ,@((Join-Path $home_ $f), 4) }
    $skip = '^(Windows|Program Files|Program Files \(x86\)|ProgramData|\$Recycle\.Bin|System Volume Information|Users|Recovery|PerfLogs)$'
    foreach ($d in [System.IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq "Fixed" }) {
        foreach ($top in Get-ChildItem -LiteralPath $d.RootDirectory.FullName -Directory -ErrorAction SilentlyContinue) {
            if ($top.Name -notmatch $skip) { $places += ,@($top.FullName, 3) }
        }
    }
    foreach ($pl in $places) {
        $root, $depth = $pl
        if (-not $root -or -not (Test-Path -LiteralPath $root)) { continue }
        foreach ($c in (Join-Path $root "content\citadel_addons"), (Join-Path $root "citadel_addons")) {
            if (Test-Path -LiteralPath (Join-Path $c $tail)) { return (Join-Path $c "funny_valentine") }
        }
        $hit = Get-ChildItem -LiteralPath $root -Directory -Recurse -Depth $depth -Filter "citadel_addons" -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName $tail) } | Select-Object -First 1
        if ($hit) { return (Join-Path $hit.FullName "funny_valentine") }
    }
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = "Pick your CSDK12 folder (the one with 'content' and 'game' inside)"
        if ($dlg.ShowDialog() -eq "OK") {
            $p = Join-Path $dlg.SelectedPath "content\citadel_addons\funny_valentine"
            if (Test-Path -LiteralPath $p) { return $p }
        }
    } catch { }
    throw "Couldn't find CSDK12\content\citadel_addons\funny_valentine. Drag your CSDK12 folder onto the .bat file."
}

# compiled file -> the step that makes it
$Expected = [ordered]@{
    "materials\funny_valentine\fv_revolver.vmat_c"               = "CSDK12: right-click the addon > Compile All Assets"
    "materials\funny_valentine\fv_d4c.vmat_c"                    = "CSDK12: right-click the addon > Compile All Assets"
    "particles\funny_valentine\d4c_hotel.vpcf_c"                 = "CSDK12: right-click the addon > Compile All Assets"
    "particles\abilities\doorman\doorman_hotel_debuff.vpcf_c"    = "CSDK12: right-click the addon > Compile All Assets"
    "models\heroes_wip\doorman_v2\doorman.vmdl_c"                = "VMDL Compiler: model doorman.vmdl, preset doorman, compile"
    "models\heroes_wip\doorman_v2\fv_d4c_hotel.vmdl_c"           = "VMDL Compiler: model fv_d4c_hotel.vmdl, compile"
}

try {
    $addon = Find-Addon
    $csdk = Split-Path (Split-Path (Split-Path $addon))
    $game = Join-Path $csdk "game\citadel_addons\funny_valentine"
    Say "Addon: $addon"

    if ($Check) {
        $missing = 0
        $installed = Get-Item -LiteralPath (Join-Path $addon "models\heroes_wip\doorman_v2\funny_valentine.dmx") -ErrorAction SilentlyContinue
        foreach ($k in $Expected.Keys) {
            $f = Get-Item -LiteralPath (Join-Path $game $k) -ErrorAction SilentlyContinue
            $stale = $f -and $installed -and $k -like "*doorman.vmdl_c" -and $f.LastWriteTime -lt $installed.LastWriteTime
            if ($f -and -not $stale) { Say ("  ok       " + $k) "Green" }
            elseif ($stale) { Say ("  OLD      $k  (compiled before the update) -> " + $Expected[$k]) "Yellow"; $missing++ }
            else { Say ("  MISSING  $k  -> " + $Expected[$k]) "Red"; $missing++ }
        }
        if ($missing -eq 0) { Say "Everything's built. In the VMDL Compiler click 'make vpk...' and upload the vpk." "Green" }
        return
    }

    $src = Join-Path $PSScriptRoot "addon"
    if (-not (Test-Path -LiteralPath $src)) { throw "No 'addon' folder next to this script - unzip the whole update first." }
    $now = Get-Date
    $n = 0
    foreach ($f in Get-ChildItem -LiteralPath $src -File -Recurse) {
        $rel = $f.FullName.Substring($src.Length).TrimStart('\', '/')
        $dst = Join-Path $addon $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
        Copy-Item -LiteralPath $f.FullName -Destination $dst -Force
        (Get-Item -LiteralPath $dst).LastWriteTime = $now
        Say "  $rel"
        $n++
    }
    Say ""
    Say "Copied $n files. Now:" "Green"
    Say "  1. CSDK12: right-click the funny_valentine addon > Compile All Assets (materials + effects)." "Cyan"
    Say "  2. VMDL Compiler: model doorman.vmdl, preset doorman > compile." "Cyan"
    Say "  3. VMDL Compiler: model fv_d4c_hotel.vmdl > compile (it's D4C, a plain prop)." "Cyan"
    Say "  4. Run 'Check FV update.bat'. When it's all ok: make vpk... and upload the vpk." "Cyan"
} catch {
    Say ""
    Say "Failed: $($_.Exception.Message)" "Red"
    exit 1
}
