@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0release.ps1" %*
if errorlevel 1 (
  echo.
  echo Phat hanh that bai. Xem loi o tren.
  pause
  exit /b 1
)
echo.
echo Phat hanh hoan tat.
pause
