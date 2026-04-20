@echo off
:: ============================================================
:: lab_localize.cmd  –  CCES Lab Localisation Launcher
:: Replaces: Gaia-Settings.cmd, Windows-Localize.cmd
::
:: Runs lab_localize.py elevated via Python.
:: Place alongside lab_localize.py in C:\LabConfig\
:: ============================================================
cls
echo.
echo  ######################################################
echo.
echo  ###       CCES Lab Localisation Tool              ###
echo.
echo  ###       Starting - please wait...               ###
echo.
echo  ######################################################
echo.

:: Require elevation - re-launch self elevated if needed
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo  Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Prefer pwsh (PS 7), fall back to python.exe directly
where pwsh >nul 2>&1
if %errorlevel% equ 0 (
    pwsh -NoProfile -Command "python '%~dp0lab_localize.py'"
) else (
    python "%~dp0lab_localize.py"
)

pause
