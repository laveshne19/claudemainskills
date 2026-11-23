@echo off
title Tally Connect (demo)
echo Starting the demo with a simulated Tally. Nothing here touches your real books.
echo.
where python >nul 2>nul
if %errorlevel%==0 (
  python -m tally_connect.cli app --demo
) else (
  py -3 -m tally_connect.cli app --demo
)
if errorlevel 1 (
  echo.
  echo The demo did not start. Run INSTALL.bat first, or send a screenshot of this window.
  pause
)
