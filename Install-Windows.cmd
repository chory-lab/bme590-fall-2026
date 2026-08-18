@echo off
REM Double-click me on Windows. This is only a wrapper: it runs install.ps1
REM from this folder with PowerShell's execution policy bypassed for this one
REM process (no system setting is changed, no administrator rights needed).
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" echo Installer exited with code %RC%.
echo Press any key to close this window.
pause >nul
exit /b %RC%
