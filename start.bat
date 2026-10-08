@echo off
title Skyrex AI Server
chcp 65001 > nul
echo ====================================================
echo  Skyrex Computers - AI Assistant & Web Server
echo ====================================================
echo.
echo Сервер доступен по адресам:
echo  - Локально на этом ПК:        http://localhost:5000
echo  - В вашей локальной сети:     http://192.168.0.159:5000
echo.
echo Нажмите Ctrl+C для остановки сервера.
echo ====================================================
echo.
python server.py
pause
