@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Skyrex Computers - Сбор цен и обновление каталога

set "PYTHON_EXE=python"
if exist "%LocalAppData%\Python\bin\python.exe" (
    set "PYTHON_EXE=%LocalAppData%\Python\bin\python.exe"
) else (
    where python >nul 2>&1
)

"%PYTHON_EXE%" scraper_menu.py
if errorlevel 1 (
    echo.
    echo [!] Произошла ошибка при запуске.
    pause
)
