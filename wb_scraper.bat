@echo off
chcp 65001 > nul
set "PYTHON_EXE=C:\Users\user\AppData\Local\Python\bin\python.exe"

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" run_scraper.py %*
) else (
    python run_scraper.py %*
)
