@echo off
rem Runs one sync. Scheduled three times a day by install_agent.ps1. Safe to run by hand too.
cd /d "%~dp0.."
if not exist "%USERPROFILE%\.nalandaaccounts" mkdir "%USERPROFILE%\.nalandaaccounts"
where python >nul 2>nul
if %errorlevel%==0 (
  python -m sync_agent --config "%USERPROFILE%\.nalandaaccounts\agent.json" >> "%USERPROFILE%\.nalandaaccounts\run.log" 2>&1
) else (
  py -3 -m sync_agent --config "%USERPROFILE%\.nalandaaccounts\agent.json" >> "%USERPROFILE%\.nalandaaccounts\run.log" 2>&1
)
exit /b 0
