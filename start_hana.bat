@echo off
cd /d "%~dp0"
if exist "%~dp0dist\Hana\Hana.exe" (
    start "Hana" "%~dp0dist\Hana\Hana.exe"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_hana.ps1"
)
pause
