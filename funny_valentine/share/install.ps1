# Funny Valentine for Deadlock - installer.
# Finds Deadlock, makes sure the game loads mods from citadel\addons, and copies the mod in.
# Run it again after a Deadlock update (updates reset gameinfo.gi) or to update the mod.
param(
    [string]$DeadlockPath = "",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$ModName = "Funny Valentine"
$Marker = "funny_valentine.installed"
$DownloadUrl = "https://github.com/idkbro757/deadlock-mods/releases/download/funny-valentine/funny_valentine.vpk"

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }
function J([string[]]$parts) { $p = $parts[0]; foreach ($x in $parts[1..($parts.Count - 1)]) { $p = Join-Path $p $x }; return $p }

function Test-Deadlock($dir) {
    return $dir -and (Test-Path -LiteralPath (J @($dir, "game", "citadel", "gameinfo.gi")))
}

function Find-Deadlock {
    if ($DeadlockPath) {
        if (Test-Deadlock $DeadlockPath) { return (Resolve-Path -LiteralPath $DeadlockPath).Path }
        throw "No Deadlock install at '$DeadlockPath' (expected game\citadel\gameinfo.gi inside it)."
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

function Enable-Addons($gameinfo) {
    $text = [System.IO.File]::ReadAllText($gameinfo)
    if ($text -match '(?m)^[ \t]*Game[ \t]+citadel/addons[ \t]*\r?$') {
        Say "  gameinfo.gi already loads mods"
        return
    }
    $nl = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $re = [regex]'(?m)^([ \t]*)Game([ \t]+)citadel[ \t]*(?=\r?$)'
    if (-not $re.IsMatch($text)) { throw "gameinfo.gi doesn't look like Deadlock's (no 'Game citadel' line) - not touching it." }
    [System.IO.File]::Copy($gameinfo, "$gameinfo.bak", $true)
    $patched = $re.Replace($text, { param($m) $m.Groups[1].Value + "Game" + $m.Groups[2].Value + "citadel/addons" + $nl + $m.Value }, 1)
    [System.IO.File]::WriteAllText($gameinfo, $patched)
    Say "  gameinfo.gi now loads mods from citadel\addons (backup: gameinfo.gi.bak)"
}

function Get-Vpk {
    $here = $PSScriptRoot
    $local = Get-ChildItem -LiteralPath $here -Filter "*.vpk" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($local) { return $local.FullName }
    Say "  no .vpk next to the installer, downloading the latest build..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) "funny_valentine.vpk"
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $tmp -UseBasicParsing
    return $tmp
}

try {
    Say "== $ModName for Deadlock ==" "Magenta"
    $deadlock = Find-Deadlock
    Say "Deadlock: $deadlock"
    $citadel = J @($deadlock, "game", "citadel")
    $addons = J @($citadel, "addons")
    $markerPath = J @($addons, $Marker)
    $current = $null
    if (Test-Path -LiteralPath $markerPath) {
        $name = (Get-Content -LiteralPath $markerPath -Raw).Trim()
        if ($name -and (Test-Path -LiteralPath (J @($addons, $name)))) { $current = $name }
    }

    if ($Uninstall) {
        if ($current) { Remove-Item -LiteralPath (J @($addons, $current)) -Force; Say "Removed $current" "Green" }
        else { Say "It isn't installed (nothing to remove)." }
        if (Test-Path -LiteralPath $markerPath) { Remove-Item -LiteralPath $markerPath -Force }
        return
    }

    Enable-Addons (J @($citadel, "gameinfo.gi"))
    New-Item -ItemType Directory -Force -Path $addons | Out-Null
    $vpk = Get-Vpk
    $hash = (Get-FileHash -LiteralPath $vpk -Algorithm SHA256).Hash

    if (-not $current) {
        # same file already there under another name? reuse that slot
        foreach ($f in Get-ChildItem -LiteralPath $addons -Filter "pak*_dir.vpk" -File) {
            if ((Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash -eq $hash) { $current = $f.Name; break }
        }
    }
    if (-not $current) {
        $used = @(Get-ChildItem -LiteralPath $addons -Filter "pak*_dir.vpk" -File | ForEach-Object { $_.Name.ToLower() })
        foreach ($i in 1..99) {
            $n = "pak{0:D2}_dir.vpk" -f $i
            if ($used -notcontains $n) { $current = $n; break }
        }
        if (-not $current) { throw "citadel\addons already has pak01-pak99, no free slot." }
    }
    $dest = J @($addons, $current)
    if ((Test-Path -LiteralPath $dest) -and (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash -eq $hash) {
        Say "  already up to date ($current)"
    } else {
        Copy-Item -LiteralPath $vpk -Destination $dest -Force
        Say "  installed as citadel\addons\$current"
    }
    Set-Content -LiteralPath $markerPath -Value $current
    Say ""
    Say "Done! Start Deadlock and pick Doorman. If he's still Doorman after a game update, just run this again." "Green"
} catch {
    Say ""
    Say "Install failed: $($_.Exception.Message)" "Red"
    exit 1
}
