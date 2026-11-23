@echo off
title Tally Connect
echo Starting Tally Connect. Keep this window open while you work.
echo Open TallyPrime and your company first.
echo.
where python >nul 2>nul
if %errorlevel%==0 (
  python -m tally_connect.cli app
) else (
  py -3 -m tally_connect.cli app
)
if errorlevel 1 (
  echo.
  echo Tally Connect did not start. Run INSTALL.bat first, or send a screenshot of this window.
  pause
)
