import os
import re
import time
import random
import logging
from typing import List, Dict, Any, Optional
from curl_cffi import requests
from db.database import upsert_products, init_db

logger = logging.getLogger("citilink_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CITILINK_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}

CITILINK_CATEGORIES = {
    "gpu": {
        "title": "Видеокарты",
        "slug": "videokarty"
    },
    "cpu": {
        "title": "Процессоры",
        "slug": "processory"
    },
    "motherboard": {
        "title": "Материнские платы",
        "slug": "materinskie-platy"
    },
    "ram": {
        "title": "Оперативная память",
        "slug": "moduli-pamyati"
    },
    "ssd": {
        "title": "SSD накопители",
        "slug": "ssd-nakopiteli"
    },
    "psu": {
        "title": "Блоки питания",
        "slug": "bloki-pitaniya"
    }
}

class CitilinkScraper:
    """
    Парсер розничной сети Ситилинк на базе curl_cffi.
    Работает без блокировок, извлекает актуальные цены, артикулы и ссылки.
    """
    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy or os.getenv("CITILINK_PROXY", "").strip() or None
        self.session = requests.Session(impersonate="chrome120")
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
            logger.info(f"Using proxy for Citilink: {self.proxy.split('@')[-1] if '@' in self.proxy else self.proxy}")

    def fetch_category_items(self, category_key: str, page: int = 1, retries: int = 3) -> List[Dict[str, Any]]:
        if category_key not in CITILINK_CATEGORIES:
            logger.error(f"Unknown Citilink category: {category_key}")
            return []

        cat_info = CITILINK_CATEGORIES[category_key]
        url = f"https://www.citilink.ru/catalog/{cat_info['slug']}/?p={page}"

        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, headers=CITILINK_HEADERS, timeout=15)
                if resp.status_code == 200:
                    return self._parse_html(resp.text, category_key)
                elif resp.status_code == 404:
                    logger.info(f"Page {page} not found or category end reached.")
                    return []
                else:
                    logger.warning(f"Citilink returned HTTP {resp.status_code} on page {page} (attempt {attempt})")
                    time.sleep(attempt * 2.0)
            except Exception as e:
                logger.error(f"Citilink network error on page {page}: {e}")
                if attempt < retries:
                    time.sleep(attempt * 2.0)

        return []

    def _parse_html(self, html_text: str, category_key: str) -> List[Dict[str, Any]]:
        import html as html_lib
        products = []
        # Find all card boundaries using data-meta-product-id
        pids_iter = list(re.finditer(r'data-meta-product-id="(\d+)"', html_text))
        if not pids_iter:
            return products

        seen_ids = set()
        for i, p_match in enumerate(pids_iter):
            pid = p_match.group(1)
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            start = p_match.start()
            # Scope search strictly to this card block (up to next card or max 15000 chars)
            end = pids_iter[i + 1].start() if i + 1 < len(pids_iter) else start + 15000
            card_html = html_text[start:end]

            # 1. Real current price inside this card block
            price = None
            price_meta = re.search(r'data-meta-price="(\d+)"', card_html)
            if price_meta:
                price = int(price_meta.group(1))
            else:
                ypay = re.search(r'amount="(\d+)"', card_html)
                if ypay:
                    price = int(ypay.group(1))
                else:
                    price_text = re.search(r'MainPriceNumber[^>]*>([\d\s]+)<', card_html)
                    if price_text:
                        cleaned = re.sub(r'\s+', '', price_text.group(1))
                        if cleaned.isdigit():
                            price = int(cleaned)

            if not price or price <= 0:
                continue

            # 2. Real old price if present
            old_price = None
            old_meta = re.search(r'data-meta-old-price="(\d+)"', card_html)
            if old_meta:
                old_price = int(old_meta.group(1))
            else:
                old_text = re.search(r'OldPrice[^>]*>([\d\s]+)<', card_html)
                if old_text:
                    cleaned = re.sub(r'\s+', '', old_text.group(1))
                    if cleaned.isdigit():
                        old_price = int(cleaned)

            # 3. URL and Title inside this card block
            link_m = re.search(r'<a[^>]*href="(/product/[^"]+)"[^>]*title="([^"]+)"', card_html)
            if link_m:
                raw_url = link_m.group(1)
                raw_title = link_m.group(2)
            else:
                href_m = re.search(r'href="(/product/[^"]+)"', card_html)
                title_m = re.search(r'title="([^"]+)"', card_html)
                raw_url = href_m.group(1) if href_m else None
                raw_title = title_m.group(1) if title_m else None

            if not raw_url or not raw_title:
                continue

            full_url = f"https://www.citilink.ru{raw_url}" if raw_url.startswith("/") else raw_url
            clean_title = html_lib.unescape(raw_title)
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            clean_title = re.sub(r'^[^\wA-Za-zА-Яа-я]+', '', clean_title).strip()

            products.append({
                "id": f"citilink_{pid}",
                "shop": "Ситилинк",
                "name": clean_title,
                "category": category_key,
                "price": price,
                "old_price": old_price,
                "available": True,
                "url": full_url,
                "city_id": "moscow",
                "warranty": "12–36 мес.",
                "mark": 8,
                "comment": "Новый товар из розничной сети Ситилинк с официальной гарантией."
            })

        return products

    def run_scrape_cycle(self, categories: Optional[List[str]] = None, max_pages: int = 2) -> Dict[str, int]:
        init_db()
        target_categories = categories or list(CITILINK_CATEGORIES.keys())
        stats = {}

        logger.info(f"Начало сбора цен из Ситилинк (Категорий: {len(target_categories)}, Макс. страниц: {max_pages})...")

        for cat_key in target_categories:
            cat_name = CITILINK_CATEGORIES.get(cat_key, {}).get("title", cat_key)
            logger.info(f"==> [Ситилинк] Сбор категории: {cat_name} ({cat_key})")
            cat_total = 0

            for page in range(1, max_pages + 1):
                logger.info(f"Запрос страницы {page}...")
                items = self.fetch_category_items(cat_key, page=page)

                if not items:
                    logger.info(f"Товары на странице {page} закончились.")
                    break

                upsert_products(items)
                cat_total += len(items)
                logger.info(f"Сохранено {len(items)} товаров (Всего в категории: {cat_total})")

                # Rate limiting
                time.sleep(random.uniform(2.0, 3.5))

            stats[cat_key] = cat_total

        logger.info(f"Цикл сбора цен Ситилинк завершен! Итоги: {stats}")
        return stats
