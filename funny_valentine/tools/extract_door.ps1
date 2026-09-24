# Pulls Doorman's stock Doorway door out of YOUR Deadlock install and zips it to your Desktop,
# so it can be rebuilt with the flag while the frame and open door stay exactly as Valve made them.
# Downloads the Source 2 Viewer command-line tool (ValveResourceFormat, open source) to do the unpacking.
param([string]$DeadlockPath = "")
$ErrorActionPreference = "Stop"
$script:DeadlockPath = $DeadlockPath

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }
function J([string[]]$parts) { $p = $parts[0]; foreach ($x in $parts[1..($parts.Count - 1)]) { $p = Join-Path $p $x }; return $p }

function Test-Deadlock($dir) {
    return $dir -and (Test-Path -LiteralPath (J @($dir, "game", "citadel", "gameinfo.gi")))
}

function Find-Deadlock {
    if ($script:DeadlockPath) {
        if (Test-Deadlock $script:DeadlockPath) { return (Resolve-Path -LiteralPath $script:DeadlockPath).Path }
        throw "No Deadlock install at '$script:DeadlockPath' (expected game\citadel\gameinfo.gi inside it)."
    }
    $steamRoots = @()
    foreach ($key in "HKCU:\Software\Valve\Steam", "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam", "HKLM:\SOFTWARE\Valve\Steam") {
        try {
            $item = Get-ItemProperty -Path $key -ErrorAction Stop
            foreach ($name in "SteamPath", "InstallPath") { if ($item.$name) { $steamRoots += $item.$name } }
        } catch { }
    }
    $libraries = @()
    foreach ($root in $steamRoots | Select-Object -Unique) {
        $libraries += $root
        $vdf = J @($root, "steamapps", "libraryfolders.vdf")
        if (Test-Path -LiteralPath $vdf) {
            foreach ($m in [regex]::Matches((Get-Content -LiteralPath $vdf -Raw), '"path"\s+"([^"]+)"')) {
                $libraries += $m.Groups[1].Value -replace '\\\\', '\'
            }
        }
    }
    foreach ($drive in [System.IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq "Fixed" }) {
        $libraries += (J @($drive.RootDirectory.FullName, "SteamLibrary"))
        $libraries += (J @($drive.RootDirectory.FullName, "Program Files (x86)", "Steam"))
        $libraries += (J @($drive.RootDirectory.FullName, "Steam"))
    }
    foreach ($lib in $libraries | Select-Object -Unique) {
        $dir = J @($lib, "steamapps", "common", "Deadlock")
        if (Test-Deadlock $dir) { return $dir }
    }
    # last resort: ask
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = "Couldn't find Deadlock - pick the Deadlock folder (the one with 'game' inside it)"
        if ($dlg.ShowDialog() -eq "OK" -and (Test-Deadlock $dlg.SelectedPath)) { return $dlg.SelectedPath }
    } catch { }
    throw "Couldn't find Deadlock. Run it again with -DeadlockPath 'X:\...\steamapps\common\Deadlock'."
}

try {
    Say "== Extract Doorman's door ==" "Magenta"
    $deadlock = Find-Deadlock
    Say "Deadlock: $deadlock"
    $vpk = J @($deadlock, "game", "citadel", "pak01_dir.vpk")
    $work = Join-Path ([System.IO.Path]::GetTempPath()) "fv_door_extract"
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $work | Out-Null

    Say "  downloading Source 2 Viewer CLI (about 50 MB)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $zip = Join-Path $work "s2v.zip"
    Invoke-WebRequest -Uri "https://github.com/ValveResourceFormat/ValveResourceFormat/releases/latest/download/cli-windows-x64.zip" -OutFile $zip -UseBasicParsing
    Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $work "s2v") -Force
    $cli = Join-Path $work "s2v\Source2Viewer-CLI.exe"

    $out = Join-Path $work "doorman_door"
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    Say "  unpacking models/heroes_wip/doorman/doorman_door.vmdl_c ..."
    & $cli -i $vpk -f "models/heroes_wip/doorman/doorman_door.vmdl_c" -d -o (Join-Path $out "doorman_door.vmdl") | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $out "doorman_door.vmdl"))) { throw "Source 2 Viewer didn't produce doorman_door.vmdl" }
    # the compiled original too, so nothing gets lost in the decompile
    & $cli -i $vpk -f "models/heroes_wip/doorman/doorman_door.vmdl_c" -o (Join-Path $out "doorman_door.vmdl_c") | Out-Null
    $n = (Get-ChildItem -LiteralPath $out -File).Count

    $desktop = [Environment]::GetFolderPath("Desktop")
    $dest = Join-Path $desktop "doorman_door_stock.zip"
    if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Force }
    Compress-Archive -Path (Join-Path $out "*") -DestinationPath $dest
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    Say ""
    Say "Done - $n files zipped to: $dest" "Green"
    Say "Upload that zip at https://github.com/idkbro757/deadlock-mods/upload/claude/brave-pasteur-17l5q5 and tell Claude." "Cyan"
} catch {
    Say ""
    Say "Failed: $($_.Exception.Message)" "Red"
    exit 1
}
