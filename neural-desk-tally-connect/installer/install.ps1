# Neural Desk Tally Connect installer for Windows (PowerShell 5.1 or later)
# Run from the folder that contains this repo:  powershell -ExecutionPolicy Bypass -File installer\install.ps1
# It does not need administrator rights. It never touches your Tally data.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
function Say($m)  { Write-Host "  $m" }
function Step($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }

Step "1. Python"
$py = $null
foreach ($c in @("python", "py")) {
    try { $v = & $c --version 2>&1; if ($v -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 10) { $py = $c; break } } catch {}
}
if (-not $py) {
    Say "Python 3.10 or newer was not found. Installing Python 3.12 with winget..."
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    Say "Python is installed. Close this window, open a new PowerShell, and run this installer again."
    exit 0
}
Say "Using $py ($(& $py --version))"

Step "2. Install Tally Connect"
& $py -m pip install --upgrade pip --quiet
& $py -m pip install --upgrade "$root" --quiet
Say "Installed."
$scripts = & $py -c "import sysconfig;print(sysconfig.get_path('scripts'))"
$mcpExe = Join-Path $scripts "tally-connect-mcp.exe"
if (-not (Test-Path $mcpExe)) { $mcpExe = "tally-connect-mcp" }

Step "3. Check Tally"
Say "Open TallyPrime and load your company first."
Say "Then in Tally: F1 (Help) > Settings > Connectivity > Client/Server configuration."
Say "Set 'TallyPrime acts as' to Server or Both, port 9000. Press Esc back to the Gateway of Tally."
Read-Host "Press Enter when Tally is ready"
& $py -m tally_connect.cli doctor
if ($LASTEXITCODE -ne 0) { Say "Tally did not answer yet. The steps above are the usual fix. You can run 'tally-connect doctor' again any time." }

Step "4. Connect it to Claude"
# Claude Desktop
$cfgPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
if (Test-Path (Split-Path $cfgPath)) {
    if (Test-Path $cfgPath) { Copy-Item $cfgPath "$cfgPath.backup-$(Get-Date -Format yyyyMMddHHmmss)" }
    $json = if (Test-Path $cfgPath) { Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { [pscustomobject]@{} }
    if (-not ($json.PSObject.Properties.Name -contains "mcpServers")) { $json | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
    $entry = [pscustomobject]@{ command = $mcpExe; args = @() }
    if ($json.mcpServers.PSObject.Properties.Name -contains "tally-connect") { $json.mcpServers."tally-connect" = $entry }
    else { $json.mcpServers | Add-Member -NotePropertyName "tally-connect" -NotePropertyValue $entry }
    $json | ConvertTo-Json -Depth 10 | Set-Content $cfgPath -Encoding UTF8
    Say "Claude Desktop is set up (a backup of your old config was saved next to it)."
} else { Say "Claude Desktop was not found, skipping." }
# Claude Code
if (Get-Command claude -ErrorAction SilentlyContinue) {
    try { claude mcp add tally-connect --scope user -- $mcpExe | Out-Null; Say "Claude Code is set up." } catch { Say "Claude Code: run  claude mcp add tally-connect -- $mcpExe  yourself." }
    Say "To also add the skills: claude plugin marketplace add `"$root`"  then  claude plugin install tally-connect@neural-desk"
}

Step "5. Templates"
$tpl = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Tally Connect Templates"
& $py -m tally_connect.cli templates $tpl | Out-Null
Say "Excel templates are in: $tpl"

Step "Done"
Say "1. Fully quit Claude (also from the system tray) and open it again."
Say "2. Start a NEW chat, not a resumed one, and type:  check the Tally connection"
Say "3. If anything fails, send Claude a screenshot of the screen you are stuck on."
