@echo off
title MOX Installer
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0mox-setup.ps1" %*
pause
