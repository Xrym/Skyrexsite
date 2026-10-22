@echo off
chcp 65001 >nul
title Skyrex Deployer

echo ========================================================
echo   Skyrex Computers - Starting deployment...
echo ========================================================
echo.

if exist "%LocalAppData%\Python\bin\python.exe" (
    "%LocalAppData%\Python\bin\python.exe" "%~dp0deploy.py" %*
) else if exist "%LocalAppData%\Programs\Python\Launcher\py.exe" (
    "%LocalAppData%\Programs\Python\Launcher\py.exe" -3 "%~dp0deploy.py" %*
) else (
    echo [ERROR] Python launcher not found. Install Python or run deploy.py with a valid Python interpreter.
    pause
    exit /b 1
)

if errorlevel 1 (
    echo.
    echo [ERROR] Deployment failed. See the error above.
    pause
    exit /b 1
)

echo.
echo Deployment finished.
echo Press any key to close this window...
pause >nul
