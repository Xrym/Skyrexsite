@echo off
chcp 65001 > nul
title Skyrex Computers - Сбор комплектующих Wildberries

echo ================================================================
echo        Skyrex Computers - Сбор цен комплектующих Wildberries
echo ================================================================
echo.
echo Категории Wildberries: Видеокарты (GPU), SSD накопители,
echo                        Оперативная память (RAM), Материнские платы.
echo.
echo Запуск сбора в базу catalog.db...
echo.

set "PYTHON_EXE=python"
if exist "%LocalAppData%\Python\bin\python.exe" set "PYTHON_EXE=%LocalAppData%\Python\bin\python.exe"

"%PYTHON_EXE%" run_scraper.py --shop wildberries --pages 2

echo.
echo ================================================================
echo  Сбор завершен! Локальная база catalog.db обновлена.
echo ================================================================
echo.

set /p DEPLOY_CHOICE="Отправить обновленную базу catalog.db на сервер хостинга прямо сейчас? [Y/N]: "
if /i "%DEPLOY_CHOICE%"=="Y" (
    echo.
    echo Запуск прямой отправки базы на сервер (без Git)...
    "%PYTHON_EXE%" deploy.py --db-only
) else (
    echo.
    echo База сохранена локально. Для отправки на сервер позже выполните: python deploy.py --db-only
)

echo.
pause
