import os
import re
import time
import random
import logging
from typing import List, Dict, Any, Optional
from db.database import upsert_products, init_db

logger = logging.getLogger("onlinetrade_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ONLINETRADE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

ONLINETRADE_CATEGORIES = {
    "gpu": {
        "title": "Видеокарты",
        "slug": "videokarty-c338"
    },
    "cpu": {
        "title": "Процессоры",
        "slug": "processory-c342"
    },
    "motherboard": {
        "title": "Материнские платы",
        "slug": "materinskie_platy-c340"
    },
    "ram": {
        "title": "Оперативная память",
        "slug": "operativnaya_pamyat-c341"
    },
    "ssd": {
        "title": "SSD накопители",
        "slug": "ssd_diski-c294"
    },
    "psu": {
        "title": "Блоки питания",
        "slug": "bloki_pitaniya-c339"
    },
    "cooler": {
        "title": "Кулеры для процессоров",
        "slug": "kulery_dlya_protsessorov-c1482"
    },
    "case": {
        "title": "Корпуса",
        "slug": "korpusa-c1323"
    }
}

class OnlineTradeScraper:
    """
    Парсер розничной сети ОнлайнТрейд (onlinetrade.ru).
    Поддерживает браузерные сессии Playwright для прохождения проверки Servicepipe
    и сохранение актуальных цен, ссылок и названий в каталог SQLite.
    """
    def __init__(self, headless: bool = True):
        self.headless = headless

    def _parse_html_content(self, html_text: str, category_key: str) -> List[Dict[str, Any]]:
        """Parses cards from OnlineTrade HTML."""
        import html as html_lib
        products = []

        # Find item blocks via common class or ID patterns in OnlineTrade
        # OnlineTrade items typically have id="item_XXXXX" or class="indexGoods__item"
        item_matches = list(re.finditer(r'(?:id=["\']item_(\d+)["\']|class=["\'][^"\']*indexGoods__item[^"\']*["\'])', html_text))
        if not item_matches:
            # Fallback regex searching for item links and prices
            pattern = re.compile(
                r'<a[^>]*href=["\'](/catalogue/[^"\']+item-(\d+)\.html)["\'][^>]*>(.*?)</a>.*?'
                r'(?:class=["\'][^"\']*price[^"\']*["\'][^>]*>([\d\s]+)\s*(?:₽|руб)?)',
                re.DOTALL | re.IGNORECASE
            )
            for m in pattern.finditer(html_text):
                url, pid, title_raw, price_raw = m.groups()
                clean_price = int(re.sub(r'\D', '', price_raw))
                clean_title = re.sub(r'<[^>]+>', '', title_raw).strip()
                if clean_price > 0 and len(clean_title) > 3:
                    products.append({
                        "id": f"onlinetrade_{pid}",
                        "shop": "ОнлайнТрейд",
                        "name": html_lib.unescape(clean_title),
                        "category": category_key,
                        "price": clean_price,
                        "old_price": None,
                        "available": True,
                        "url": f"https://www.onlinetrade.ru{url}",
                        "city_id": "moscow",
                        "warranty": "12–36 мес.",
                        "mark": 8,
                        "comment": "Новый товар из розничной сети ОнлайнТрейд с официальной гарантией."
                    })
            return products

        seen_ids = set()
        for i, match in enumerate(item_matches):
            start = match.start()
            end = item_matches[i + 1].start() if i + 1 < len(item_matches) else start + 12000
            card_html = html_text[start:end]

            # Product ID
            pid_match = re.search(r'item-(\d+)\.html|id=["\']item_(\d+)["\']', card_html)
            pid = pid_match.group(1) or pid_match.group(2) if pid_match else str(random.randint(100000, 999999))
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            # Price
            price = None
            price_m = re.search(r'class=["\'][^"\']*price[^"\']*["\'][^>]*>([\d\s]+)', card_html)
            if price_m:
                digits = re.sub(r'\D', '', price_m.group(1))
                if digits.isdigit():
                    price = int(digits)

            if not price or price <= 0:
                continue

            # Link & Title
            link_m = re.search(r'<a[^>]*href=["\'](/catalogue/[^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', card_html)
            if link_m:
                raw_url = link_m.group(1)
                raw_title = link_m.group(2)
            else:
                a_m = re.search(r'<a[^>]*href=["\'](/catalogue/[^"\']+)["\'][^>]*>(.*?)</a>', card_html, re.DOTALL)
                if a_m:
                    raw_url = a_m.group(1)
                    raw_title = re.sub(r'<[^>]+>', '', a_m.group(2)).strip()
                else:
                    continue

            full_url = f"https://www.onlinetrade.ru{raw_url}" if raw_url.startswith("/") else raw_url
            clean_title = html_lib.unescape(raw_title).strip()

            products.append({
                "id": f"onlinetrade_{pid}",
                "shop": "ОнлайнТрейд",
                "name": clean_title,
                "category": category_key,
                "price": price,
                "old_price": None,
                "available": True,
                "url": full_url,
                "city_id": "moscow",
                "warranty": "12–36 мес.",
                "mark": 8,
                "comment": "Новый товар из розничной сети ОнлайнТрейд с официальной гарантией."
            })

        return products

    async def fetch_category_playwright(self, category_key: str, max_pages: int = 0) -> List[Dict[str, Any]]:
        """
        Парсит страницы категории через Playwright с защитными задержками.
        max_pages=0 означает парсить ВСЕ доступные страницы до конца каталога.
        """
        from playwright.async_api import async_playwright

        if category_key not in ONLINETRADE_CATEGORIES:
            return []

        cat_info = ONLINETRADE_CATEGORIES[category_key]
        base_slug = cat_info['slug']
        all_category_products = []
        seen_product_ids = set()

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768}
                )
                page = await context.new_page()

                current_page = 1
                while True:
                    if max_pages > 0 and current_page > max_pages:
                        logger.info(f"Достигнут лимит страниц ({max_pages}) для категории {category_key}.")
                        break

                    page_url = (
                        f"https://www.onlinetrade.ru/catalogue/{base_slug}/"
                        if current_page == 1
                        else f"https://www.onlinetrade.ru/catalogue/{base_slug}/?page={current_page}"
                    )

                    logger.info(f"[{cat_info['title']}] Запрос страницы {current_page}: {page_url}")
                    try:
                        await page.goto(page_url, wait_until="commit", timeout=25000)
                    except Exception as e:
                        logger.warning(f"Ошибка загрузки страницы {current_page}: {e}")
                        break

                    # Случайная пауза для имитации человека и выполнения скрипта (3.5 - 5.5 сек)
                    sleep_time = random.uniform(3.5, 5.5)
                    await page.wait_for_timeout(int(sleep_time * 1000))

                    content = await page.content()
                    page_items = self._parse_html_content(content, category_key)

                    # Фильтруем дубликаты
                    new_items = []
                    for itm in page_items:
                        if itm["id"] not in seen_product_ids:
                            seen_product_ids.add(itm["id"])
                            new_items.append(itm)

                    if not new_items:
                        logger.info(f"[{cat_info['title']}] Товары на странице {current_page} закончились (Конец категории).")
                        break

                    all_category_products.extend(new_items)
                    # Сразу сохраняем страницу в базу данных
                    upsert_products(new_items)
                    logger.info(f"[{cat_info['title']}] Стр. {current_page}: спарсено {len(new_items)} новых товаров (Всего: {len(all_category_products)})")

                    # Проверяем, есть ли кнопка следующей страницы
                    next_button = await page.query_selector('.navigation__next, a[title*="Следующая"], .paginator a.next')
                    has_more = bool(next_button)

                    if not has_more and current_page > 1:
                        logger.info(f"[{cat_info['title']}] Последняя страница каталога достигнута.")
                        break

                    current_page += 1

                    # Дополнительная безопасная пауза между переходами
                    between_pages_delay = random.uniform(2.5, 4.0)
                    time.sleep(between_pages_delay)

                await browser.close()
        except Exception as e:
            logger.error(f"Playwright scrape error for {category_key}: {e}")

        return all_category_products

    def run_scrape_cycle(self, categories: Optional[List[str]] = None, max_pages: int = 0) -> Dict[str, int]:
        """
        Запускает полный цикл сбора по всем категориям с безопасными интервалами.
        max_pages=0 парсит ВСЕ страницы до конца.
        """
        import asyncio
        init_db()
        target_categories = categories or list(ONLINETRADE_CATEGORIES.keys())
        stats = {}

        mode_str = f"ВСЕ страницы (до конца каталога)" if max_pages == 0 else f"до {max_pages} страниц"
        logger.info(f"Запуск полного сбора цен ОнлайнТрейд ({len(target_categories)} категорий, режим: {mode_str})...")

        for cat_key in target_categories:
            cat_name = ONLINETRADE_CATEGORIES.get(cat_key, {}).get("title", cat_key)
            logger.info(f"=========================================================")
            logger.info(f"==> НАЧАЛО СБОРА КАТЕГОРИИ: {cat_name} ({cat_key})")
            logger.info(f"=========================================================")

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        items = pool.submit(asyncio.run, self.fetch_category_playwright(cat_key, max_pages=max_pages)).result()
                else:
                    items = asyncio.run(self.fetch_category_playwright(cat_key, max_pages=max_pages))
            except Exception:
                items = asyncio.run(self.fetch_category_playwright(cat_key, max_pages=max_pages))

            stats[cat_key] = len(items)
            logger.info(f"Завершена категория {cat_name}. Собрано: {len(items)} позиций.")

            # Безопасная пауза перед переходом к следующей категории (10 - 16 секунд)
            inter_cat_delay = random.uniform(10.0, 16.0)
            logger.info(f"Безопасная пауза перед следующей категорией: {inter_cat_delay:.1f} сек...")
            time.sleep(inter_cat_delay)

        logger.info(f"Полный цикл сбора ОнлайнТрейд успешно завершён! Итоги: {stats}")
        return stats
