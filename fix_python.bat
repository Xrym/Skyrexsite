@echo off
chcp 65001 > nul
title Восстановление команды python

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ========================================================
    echo  Запрос прав Администратора...
    echo  Пожалуйста, нажмите "Да" в появившемся окне Windows UAC.
    echo ========================================================
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo ========================================================
echo  Удаление поврежденного файла C:\Windows\System32\python
echo ========================================================
echo.

if exist "C:\Windows\System32\python" (
    del /f /q "C:\Windows\System32\python"
    if exist "C:\Windows\System32\python" (
        echo [ОШИБКА] Не удалось удалить файл C:\Windows\System32\python.
    ) else (
        echo [УСПЕХ] Файл C:\Windows\System32\python успешно удален!
        echo Теперь стандартная команда 'python' работает корректно.
    )
) else (
    echo [ИНФО] Файл C:\Windows\System32\python уже удален!
)

echo.
echo Нажмите любую клавишу для закрытия...
pause > nul
