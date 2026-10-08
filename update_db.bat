@echo off
chcp 65001 > nul
title Skyrex Computers - Full Catalog Scraper
echo ================================================================
echo        Skyrex Computers - Polnyi parsing OnlineTrade
echo ================================================================
echo.
echo Mode: ALL PAGES TO THE END (pages=0)
echo Delays: Safe random delays (3.5 - 5.5s per page, 12s category)
echo.
echo Vnimanie: otkroetsya okno brauzera Chrome.
echo Esli poyavitsya zashchita s polzunkom - povernite kartinku rukami.
echo Posle pervogo raza sessiya sokhranitsya dlya vseh stranic!
echo.
python run_scraper.py --shop onlinetrade --pages 0

echo.
echo ================================================================
echo        Obnovlenie bazy dannyh zaversheno uspeshno!
echo ================================================================
pause
