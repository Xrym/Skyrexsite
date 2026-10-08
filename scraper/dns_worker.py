import os
import time
import random
import logging
from typing import List, Dict, Any, Optional
from curl_cffi import requests
from db.database import upsert_products, init_db

logger = logging.getLogger("dns_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Стандартные категории каталога ДНС с кодами категорий
DNS_CATEGORIES = {
    "gpu": {
        "title": "Видеокарты",
        "url_path": "videokarty",
        "category_id": "17a8882416404e77"
    },
    "cpu": {
        "title": "Процессоры",
        "url_path": "processory",
        "category_id": "17a899cd16404e77"
    },
    "motherboard": {
        "title": "Материнские платы",
        "url_path": "materinskie-platy",
        "category_id": "17a89a0416404e77"
    },
    "ram": {
        "title": "Оперативная память",
        "url_path": "operativnaya-pamyat-dimm",
        "category_id": "17a89a3916404e77"
    },
    "ssd": {
        "title": "SSD накопители",
        "url_path": "ssd-nakopiteli",
        "category_id": "17a89e9416404e77"
    },
    "psu": {
        "title": "Блоки питания",
        "url_path": "bloki-pitaniya",
        "category_id": "17a89c2216404e77"
    }
}

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.dns-shop.ru",
    "Referer": "https://www.dns-shop.ru/",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}

# Cookie для Москвы (по умолчанию)
DEFAULT_COOKIES = {
    "city_path": "moscow",
    "current_path": "b9d02336-7c9d-11e2-9b24-001517c526f0"
}

class DnsScraper:
    """
    Фоновый скрапер для сайта ДНС на базе curl_cffi с эмуляцией TLS Chrome и защитой от блокировок.
    """
    def __init__(self, proxy: Optional[str] = None):
        # Читаем прокси из аргумента или переменной окружения DNS_PROXY
        self.proxy = proxy or os.getenv("DNS_PROXY", "").strip() or None
        self.session = requests.Session(impersonate="chrome120")
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
            logger.info(f"Using proxy: {self.proxy.split('@')[-1] if '@' in self.proxy else self.proxy}")

    def fetch_category_items(self, category_key: str, page: int = 1, retries: int = 3) -> List[Dict[str, Any]]:
        """Запрашивает список товаров категории через внутренний API каталога ДНС."""
        if category_key not in DNS_CATEGORIES:
            logger.error(f"Unknown category: {category_key}")
            return []

        cat_info = DNS_CATEGORIES[category_key]
        url = f"https://www.dns-shop.ru/catalog/json/get-products-list/"
        params = {
            "p": page,
            "i": cat_info["category_id"],
            "mode": "simple"
        }

        for attempt in range(1, retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=DEFAULT_HEADERS,
                    cookies=DEFAULT_COOKIES,
                    timeout=15
                )

                if response.status_code == 200:
                    try:
                        data = response.json()
                        return self._parse_dns_products(data, category_key)
                    except Exception as json_err:
                        logger.warning(f"Failed to parse JSON on page {page}: {json_err}")
                        return []
                elif response.status_code in [401, 403]:
                    logger.warning(f"WAF Protection (HTTP {response.status_code}). Попытка {attempt}/{retries}.")
                    if attempt < retries:
                        time.sleep(attempt * 4.0)
                    else:
                        logger.error(f"Blocked by WAF on category {category_key}, page {page}. Consider using residential proxies.")
                        return []
                else:
                    logger.warning(f"DNS returned status {response.status_code} for page {page}")
                    time.sleep(attempt * 2.0)

            except Exception as e:
                logger.error(f"Network error on attempt {attempt}: {e}")
                if attempt < retries:
                    time.sleep(attempt * 2.0)

        return []

    def _parse_dns_products(self, data: dict, category_key: str) -> List[Dict[str, Any]]:
        """Извлекает структурированные данные товаров из JSON ответа ДНС."""
        products = []
        raw_list = data.get("data", {}).get("products", [])

        for item in raw_list:
            try:
                prod_id = f"dns_{item.get('id') or item.get('code')}"
                name = item.get("title") or item.get("name")
                price_data = item.get("price", {})
                price = int(price_data.get("current", 0))
                old_price = price_data.get("previous")
                link = item.get("link", "")
                if link and not link.startswith("http"):
                    link = f"https://www.dns-shop.ru{link}"

                status = item.get("status", {})
                available = status.get("available", True)

                if name and price > 0:
                    products.append({
                        "id": prod_id,
                        "shop": "DNS",
                        "name": name.strip(),
                        "category": category_key,
                        "price": price,
                        "old_price": int(old_price) if old_price else None,
                        "available": available,
                        "url": link,
                        "city_id": "moscow",
                        "warranty": "36 мес.",
                        "mark": 8,
                        "comment": f"Новый товар из розничной сети DNS-Shop. Гарантия 36 месяцев."
                    })
            except Exception:
                continue

        return products

    def run_scrape_cycle(self, categories: Optional[List[str]] = None, max_pages: int = 3) -> Dict[str, int]:
        """
        Запускает цикл сбора товаров по выбранным категориям с соблюдением задержек.
        """
        init_db()
        target_categories = categories or list(DNS_CATEGORIES.keys())
        stats = {}

        logger.info(f"Начало сбора каталога ДНС (Категорий: {len(target_categories)}, Макс. страниц на категорию: {max_pages})...")

        for cat_key in target_categories:
            cat_name = DNS_CATEGORIES.get(cat_key, {}).get("title", cat_key)
            logger.info(f"==> Обработка категории: {cat_name} ({cat_key})")
            cat_total = 0

            for page in range(1, max_pages + 1):
                logger.info(f"Запрос страницы {page}...")
                items = self.fetch_category_items(cat_key, page=page)

                if not items:
                    logger.info(f"Товаров на странице {page} нет или достигнут конец списка.")
                    break

                upsert_products(items)
                cat_total += len(items)
                logger.info(f"Успешно сохранено {len(items)} товаров (Всего в категории: {cat_total})")

                # Rate-limiting: случайная задержка 2.5–5 секунд
                delay = random.uniform(2.5, 4.5)
                time.sleep(delay)

            stats[cat_key] = cat_total

        logger.info(f"Цикл сбора цен завершен! Итоги: {stats}")
        return stats
