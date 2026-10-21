@echo off
chcp 65001 >nul
title Skyrex Deployer

echo ========================================================
echo   Skyrex Computers - Starting deployment...
echo ========================================================
echo.

python "%~dp0deploy.py" %*

echo.
echo Press any key to close this window...
pause >nul
