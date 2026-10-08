import time
import threading
import logging
from .dns_worker import DnsScraper

logger = logging.getLogger("scraper_scheduler")

class BackgroundPriceScheduler:
    """
    Фоновый планировщик, который запускает обновление цен по расписанию
    (например, раз в 12 часов), не блокируя основной сервер и не нагружая сайт запросами.
    """
    def __init__(self, interval_hours: int = 12, max_pages: int = 2):
        self.interval_seconds = interval_hours * 3600
        self.max_pages = max_pages
        self.scraper = DnsScraper()
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="PriceScraperThread")
        self._thread.start()
        logger.info(f"Background Price Scheduler started (Interval: {self.interval_seconds // 3600} hours).")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            logger.info("Background Price Scheduler stopped.")

    def _run_loop(self):
        # Initial delay before first background crawl (to let server start fast)
        time.sleep(10)
        while not self._stop_event.is_set():
            try:
                logger.info("Executing periodic catalog price update...")
                self.scraper.run_scrape_cycle(max_pages=self.max_pages)
            except Exception as e:
                logger.error(f"Error during periodic scraping: {e}")

            # Sleep in small increments to allow graceful shutdown
            for _ in range(self.interval_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1)
