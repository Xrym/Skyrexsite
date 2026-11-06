@echo off
chcp 65001 > nul
title Skyrex Computers - Сбор Б/У цен Avito

echo ================================================================
echo        Skyrex Computers - Сбор Б/У цен комплектующих Avito
echo ================================================================
echo.
echo Категории Avito: Видеокарты (GPU), Процессоры (CPU), ОЗУ (RAM),
echo                  Материнские платы, SSD накопители, Блоки питания.
echo.
echo Запуск браузера для сбора рыночных цен и обновления expert_components...
echo При запросе проверки человека подтвердите ее один раз в окне браузера.
echo.

set "PYTHON_EXE=python"
if exist "%LocalAppData%\Python\bin\python.exe" set "PYTHON_EXE=%LocalAppData%\Python\bin\python.exe"

"%PYTHON_EXE%" run_scraper.py --shop avito

echo.
echo ================================================================
echo  Сбор завершен! Локальная база catalog.db обновлена.
echo ================================================================
echo.

set /p DEPLOY_CHOICE="Отправить обновленную базу catalog.db на сервер хостинга прямо сейчас? [Y/N]: "
if /i "%DEPLOY_CHOICE%"=="Y" (
    echo.
    echo Запуск отправки базы на сервер...
    "%PYTHON_EXE%" deploy.py --db-only
) else (
    echo.
    echo База сохранена локально. Для отправки на сервер позже выполните: python deploy.py --db-only
)

echo.
pause

