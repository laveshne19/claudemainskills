# Installs the Nalanda Accounts sync agent on the PC that has TallyPrime (PowerShell 5.1 or later).
#   powershell -ExecutionPolicy Bypass -File sync_agent\install_agent.ps1
# Optional:  -Times "10:00","14:30","20:00"   (three runs a day; pick times that avoid other Tally jobs)
param([string[]]$Times = @("10:00", "14:30", "20:00"))
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$home2 = Join-Path $env:USERPROFILE ".nalandaaccounts"
function Say($m)  { Write-Host "  $m" }
function Step($m) { Write-Host ""; Write-Host "== $m" -ForegroundColor Cyan }

Step "1. Python and Tally Connect"
$py = $null
foreach ($c in @("python", "py")) { try { $v = & $c --version 2>&1; if ($v -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 10) { $py = $c; break } } catch {} }
if (-not $py) { Say "Python 3.10 or newer is needed. Install it from python.org (tick 'Add to PATH'), then run this again."; exit 1 }
& $py -c "import tally_connect" 2>$null
if ($LASTEXITCODE -ne 0) { Say "Tally Connect is not installed on this PC. Install it first (the desktop zip, INSTALL.bat), then run this again."; exit 1 }
Say "Python and Tally Connect found."

Step "2. Settings"
New-Item -ItemType Directory -Force -Path $home2 | Out-Null
$cfg = Join-Path $home2 "agent.json"
if (-not (Test-Path $cfg)) {
    $url = Read-Host "  Portal address (for example https://nalandaaccounts.netlify.app)"
    $sec = Read-Host "  Sync key (paste it, it is not shown again)" -AsSecureString
    $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    $obj = Get-Content (Join-Path $PSScriptRoot "agent.example.json") -Raw | ConvertFrom-Json
    $obj.portal_url = $url.Trim().TrimEnd("/"); $obj.sync_key = $key
    $obj | ConvertTo-Json -Depth 5 | Set-Content $cfg -Encoding UTF8
    # only this Windows user may read the file, because it holds the sync key
    icacls $cfg /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
    Say "Saved $cfg"
} else { Say "Keeping your existing settings in $cfg" }

Step "3. Test read from Tally (nothing is sent)"
Say "Open TallyPrime with the company loaded first."
Read-Host "  Press Enter when Tally is open"
Push-Location $root
& $py -m sync_agent --config $cfg --dry-run --limit 5 --debug-dump (Join-Path $home2 "dump")
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { Say "The test did not finish (code $code). Read the message above. Send it to Claude with a screenshot of Tally and we will fix it. Nothing was scheduled."; exit $code }
Say "The test read worked. If any statement said it does not add up to Tally's balance, send the folder $home2\dump to Claude before relying on the portal."

Step "4. Schedule three syncs a day"
$bat = Join-Path $PSScriptRoot "run_sync.bat"
foreach ($t in $Times) {
    $name = "Nalanda Accounts Sync " + $t.Replace(":", "")
    schtasks /Create /TN $name /TR "`"$bat`"" /SC DAILY /ST $t /F | Out-Null
    Say "Scheduled: $name at $t"
}
Say "These run while you are signed in to Windows. If Tally is closed at that time the run is skipped and the next one catches up."

Step "5. First real sync now?"
$a = Read-Host "  Send the data to the portal now? (y/N)"
if ($a -match "^[yY]") { Push-Location $root; & $py -m sync_agent --config $cfg; Pop-Location }
Step "Done"
Say "Log of every run: $home2\run.log and $home2\sync_agent.log"
