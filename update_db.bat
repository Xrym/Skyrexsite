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
echo Vnimanie: process mozhet zanyat 15-40 minut.
echo Mozhno svernut eto okno, ono rabotaet v fone.
echo.
python run_scraper.py --shop onlinetrade --pages 0

echo.
echo ================================================================
echo        Obnovlenie bazy dannyh zaversheno uspeshno!
echo ================================================================
pause
