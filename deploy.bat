@echo off
chcp 65001 >nul
title Skyrex Deployer

echo ========================================================
echo   Skyrex Computers - Запуск выгрузки на сервер...
echo ========================================================
echo.

python "%~dp0deploy.py" %*

echo.
echo Для закрытия окна нажмите любую клавишу...
pause >nul
