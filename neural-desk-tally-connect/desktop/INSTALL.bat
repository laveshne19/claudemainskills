@echo off
title Install Tally Connect
echo Installing Tally Connect. This takes a minute or two.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install.ps1"
echo.
pause
