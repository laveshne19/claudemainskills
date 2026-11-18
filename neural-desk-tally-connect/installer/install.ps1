# Neural Desk Tally Connect installer for Windows (PowerShell 5.1 or later)
# Run by double clicking INSTALL.bat, or:  powershell -ExecutionPolicy Bypass -File installer\install.ps1
# No administrator rights needed. It never touches your Tally data.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
function Say($m)  { Write-Host "  $m" }
function Step($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }

Step "1. Python"
$py = $null
foreach ($c in @("python", "py")) {
    try {
        $v = & $c --version 2>&1
        if ($v -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 10) { $py = $c; break }
    } catch {}
}
if (-not $py) {
    Say "Python 3.10 or newer was not found. Installing Python 3.12 with winget..."
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    Say "Python is installed. Close this window, then run INSTALL.bat again."
    exit 0
}
Say "Using $py ($(& $py --version))"

Step "2. Install Tally Connect"
& $py -m pip install --upgrade pip --quiet
$wheel = Get-ChildItem -Path (Join-Path $root "wheel") -Filter "*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($wheel) { & $py -m pip install --upgrade --force-reinstall $wheel.FullName --quiet; Say "Installed from $($wheel.Name)." }
else        { & $py -m pip install --upgrade "$root" --quiet; Say "Installed from source." }
& $py -c "import tally_connect;print('  Version', tally_connect.__version__)"

Step "3. Desktop shortcuts"
try {
    $desk = [Environment]::GetFolderPath("Desktop")
    $ws = New-Object -ComObject WScript.Shell
    foreach ($pair in @(@("Tally Connect", "Start Tally Connect.bat"), @("Tally Connect Demo", "Start Demo (no Tally needed).bat"))) {
        $target = Join-Path $root ("desktop\" + $pair[1])
        if (-not (Test-Path $target)) { $target = Join-Path $root $pair[1] }
        if (Test-Path $target) {
            $lnk = $ws.CreateShortcut((Join-Path $desk ($pair[0] + ".lnk")))
            $lnk.TargetPath = $target
            $lnk.WorkingDirectory = Split-Path $target
            $lnk.Save()
            Say "Shortcut on your Desktop: $($pair[0])"
        }
    }
} catch { Say "Could not create shortcuts ($($_.Exception.Message)). You can double click the .bat files instead." }

Step "4. Excel templates"
$tpl = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Tally Connect Templates"
& $py -m tally_connect.cli templates $tpl | Out-Null
Say "Blank Excel templates are in: $tpl"

Step "5. Check Tally (optional)"
Say "If TallyPrime is open with a company, this tells you whether Tally Connect can see it."
& $py -m tally_connect.cli doctor
if ($LASTEXITCODE -ne 0) { Say "Tally did not answer yet. That is fine for now. The Setup tab inside the app walks you through it." }

Step "6. Claude (optional)"
$ans = Read-Host "  Also connect to Claude so you can upload PDFs and photos in chat? (y/N)"
if ($ans -match "^[yY]") {
    $scripts = & $py -c "import sysconfig;print(sysconfig.get_path('scripts'))"
    $mcpExe = Join-Path $scripts "tally-connect-mcp.exe"
    if (-not (Test-Path $mcpExe)) { $mcpExe = "tally-connect-mcp" }
    $cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    if (Test-Path (Split-Path $cfgPath)) {
        if (Test-Path $cfgPath) { Copy-Item $cfgPath "$cfgPath.backup-$(Get-Date -Format yyyyMMddHHmmss)" }
        $json = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { [pscustomobject]@{} }
        if (-not ($json.PSObject.Properties.Name -contains "mcpServers")) { $json | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
        $entry = [pscustomobject]@{ command = $mcpExe; args = @() }
        if ($json.mcpServers.PSObject.Properties.Name -contains "tally-connect") { $json.mcpServers."tally-connect" = $entry }
        else { $json.mcpServers | Add-Member -NotePropertyName "tally-connect" -NotePropertyValue $entry }
        $json | ConvertTo-Json -Depth 10 | Set-Content $cfgPath -Encoding UTF8
        Say "Claude Desktop is set up (a backup of your old settings was saved next to it)."
    } else { Say "Claude Desktop was not found, skipping." }
    if (Get-Command claude -ErrorAction SilentlyContinue) {
        try { claude mcp add tally-connect --scope user -- $mcpExe | Out-Null; Say "Claude Code is set up." } catch { Say "For Claude Code run:  claude mcp add tally-connect -- $mcpExe" }
        $plug = Join-Path $root "plugin"
        if (Test-Path $plug) { Say "To add the skills: claude plugin marketplace add `"$root`"  then  claude plugin install tally-connect@neural-desk" }
    }
    Say "Fully quit Claude (also from the system tray), open it again, and start a NEW chat."
}

Step "Done"
Say "Double click 'Tally Connect Demo' on your Desktop to try it with no Tally."
Say "Double click 'Tally Connect' to use it with your real Tally."
