# -*- coding: utf-8 -*-
"""
Skyrex Computers - Avito Hardware Scraper
Модуль сбора актуальных рыночных цен на Б/У компьютерные комплектующие с Авито.
Использует Playwright с постоянным профилем пользователя (Persistent Context)
для сохранения авторизации и сессии, а также надежную фильтрацию неликвида и брака.
"""

import os
import sys
import re
import time
import random
import logging
import asyncio
import statistics
from typing import List, Dict, Any, Optional

from db.database import upsert_products, get_connection, init_db

# Configure logger
logger = logging.getLogger("avito_scraper")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

AVITO_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "gpu": {
        "title": "Видеокарты",
        "default_min_price": 3000,
        "items": [
            {"name": "AMD Radeon RX 580 8GB", "query": "RX 580 8GB", "min_price": 3500, "max_price": 9000},
            {"name": "NVIDIA GeForce GTX 1660 Super", "query": "GTX 1660 Super", "min_price": 8000, "max_price": 17000},
            {"name": "AMD Radeon RX 6600", "query": "RX 6600", "min_price": 14000, "max_price": 25000},
            {"name": "NVIDIA GeForce RTX 2060 Super", "query": "RTX 2060 Super", "min_price": 14000, "max_price": 25000},
            {"name": "AMD Radeon RX 6600 XT", "query": "RX 6600 XT", "min_price": 16000, "max_price": 28000},
            {"name": "NVIDIA GeForce RTX 3060 12GB", "query": "RTX 3060 12GB", "min_price": 20000, "max_price": 35000},
            {"name": "NVIDIA GeForce RTX 3070", "query": "RTX 3070", "min_price": 23000, "max_price": 39000},
            {"name": "NVIDIA GeForce RTX 4060", "query": "RTX 4060", "min_price": 25000, "max_price": 40000},
            {"name": "NVIDIA GeForce RTX 5050", "query": "RTX 5050", "min_price": 24000, "max_price": 38000},
            {"name": "NVIDIA GeForce RTX 5060", "query": "RTX 5060", "min_price": 32000, "max_price": 48000},
        ],
        "exclude": [
            "ноутбук", "чехол", "райзер", "кабель", "переходник", "подставка", "наклейка",
            "держатель", "коробка", "радиатор", "вентилятор", "кулер", "не рабочий",
            "на запчасти", "артефакт", "донор", "прогретая", "прогрев", "кирпич"
        ]
    },
    "cpu": {
        "title": "Процессоры",
        "default_min_price": 2000,
        "items": [
            {"name": "Intel Core i3-12100F", "query": "i3 12100F", "min_price": 3000, "max_price": 7500},
            {"name": "AMD Ryzen 5 3600", "query": "Ryzen 5 3600", "min_price": 3000, "max_price": 6500},
            {"name": "AMD Ryzen 5 5500", "query": "Ryzen 5 5500", "min_price": 4500, "max_price": 8500},
            {"name": "AMD Ryzen 5 5600", "query": "Ryzen 5 5600", "min_price": 6500, "max_price": 11500},
            {"name": "Intel Core i5-12400F", "query": "i5 12400F", "min_price": 7000, "max_price": 12500},
            {"name": "Intel Core i5-13400F", "query": "i5 13400F", "min_price": 11000, "max_price": 18500},
            {"name": "AMD Ryzen 5 7500F", "query": "Ryzen 5 7500F", "min_price": 10000, "max_price": 17500},
            {"name": "Intel Core i5-14600KF", "query": "i5 14600KF", "min_price": 15000, "max_price": 26000},
            {"name": "AMD Ryzen 7 7800X3D", "query": "Ryzen 7 7800X3D", "min_price": 30000, "max_price": 50000},
        ],
        "exclude": [
            "кулер", "ноутбук", "материнская", "пк в сборе", "компьютер", "коробка",
            "ножки", "не рабочий", "на запчасти", "донор", "погнуты"
        ]
    },
    "ram": {
        "title": "Оперативная память",
        "default_min_price": 3000,
        "items": [
            {"name": "Оперативная память 16 ГБ DDR4", "query": "DDR4 16Gb 2x8", "min_price": 5000, "max_price": 12000},
            {"name": "Оперативная память DDR4 32 ГБ", "query": "DDR4 32Gb 2x16", "min_price": 11000, "max_price": 22000},
            {"name": "DDR5 16GB", "query": "DDR5 16Gb", "min_price": 15000, "max_price": 28000},
            {"name": "Оперативная память DDR5 32GB", "query": "DDR5 32Gb 2x16", "min_price": 28000, "max_price": 52000},
        ],
        "exclude": ["ноутбук", "sodimm", "so-dimm", "серверная", "ecc", "reg", "чехол", "радиатор"]
    },
    "motherboard": {
        "title": "Материнские платы",
        "default_min_price": 3000,
        "items": [
            {"name": "Материнская плата AM4 A520", "query": "A520 AM4", "min_price": 3500, "max_price": 7500},
            {"name": "Материнская плата AM4 B550", "query": "B550 AM4", "min_price": 5500, "max_price": 14000},
            {"name": "Материнская плата LGA 1700 H610", "query": "H610 LGA 1700", "min_price": 4500, "max_price": 9500},
            {"name": "Материнская плата LGA 1700 B760", "query": "B760 LGA 1700", "min_price": 6500, "max_price": 16000},
            {"name": "Материнская плата AM5 B650", "query": "B650 AM5", "min_price": 8500, "max_price": 21000},
        ],
        "exclude": ["ноутбук", "заглушка", "пайка", "процессор", "комплект", "не рабочая", "на запчасти", "донор", "погнут"]
    },
    "ssd": {
        "title": "SSD накопители",
        "default_min_price": 1500,
        "items": [
            {"name": "SSD M.2 NVMe 256GB", "query": "SSD M.2 256Gb", "min_price": 1500, "max_price": 4500},
            {"name": "SSD M.2 NVMe 512GB", "query": "SSD M.2 512Gb", "min_price": 2500, "max_price": 7500},
            {"name": "SSD M.2 NVMe 1TB", "query": "SSD M.2 1Tb", "min_price": 5000, "max_price": 13500},
        ],
        "exclude": ["бокс", "корпус", "радиатор", "переходник", "шлейф", "адаптер", "чехол", "hdd", "жесткий"]
    },
    "psu": {
        "title": "Блоки питания",
        "default_min_price": 2000,
        "items": [
            {"name": "Блок питания 600W", "query": "Блок питания 600W", "min_price": 2500, "max_price": 7500},
            {"name": "Блок питания 700W", "query": "Блок питания 700W", "min_price": 3500, "max_price": 9500},
            {"name": "Блок питания 750W", "query": "Блок питания 750W", "min_price": 4500, "max_price": 13500},
            {"name": "Блок питания 850W", "query": "Блок питания 850W", "min_price": 6500, "max_price": 17500},
        ],
        "exclude": ["кабель", "провода", "переходник", "удлинитель", "не рабочий", "на запчасти", "донор"]
    }
}


DOM_EXTRACT_AVITO_JS = """
() => {
    const products = [];
    const seenIds = new Set();
    const cards = document.querySelectorAll('[data-marker="item"], div[class*="iva-item-root"]');

    for (const card of cards) {
        // Ссылка на карточку и название
        const linkEl = card.querySelector('a[data-marker="item-title"], a[itemprop="url"], [class*="title-root"] a');
        if (!linkEl) continue;

        const href = linkEl.getAttribute('href') || '';
        const idMatch = href.match(/_(\\d+)(?:\\?|$)/) || (card.getAttribute('data-item-id') ? [null, card.getAttribute('data-item-id')] : null);
        const pid = idMatch ? idMatch[1] : null;
        if (!pid || seenIds.has(pid)) continue;

        let title = linkEl.getAttribute('title') || linkEl.innerText.trim();
        if (!title || title.length < 3) continue;

        // Цена
        const priceEl = card.querySelector('[data-marker="item-price"], meta[itemprop="price"], [class*="price-text"], [class*="price-root"]');
        let price = 0;
        if (priceEl) {
            const metaPrice = priceEl.getAttribute('content');
            if (metaPrice && !isNaN(parseInt(metaPrice, 10))) {
                price = parseInt(metaPrice, 10);
            } else {
                const rawPrice = priceEl.innerText || '';
                const clean = rawPrice.replace(/[^0-9]/g, '');
                if (clean) price = parseInt(clean, 10);
            }
        }
        if (!price || price < 100) continue;

        // Город / Гео
        const locEl = card.querySelector('[data-marker="item-address"], [class*="geo-root"], [class*="geo-address"]');
        const city = locEl ? locEl.innerText.trim() : 'Россия';

        // Признак доставки Авито
        const hasDelivery = Boolean(card.querySelector('[data-marker="delivery-badge"], [class*="delivery"]'));

        const fullUrl = href.startsWith('http') ? href : ('https://www.avito.ru' + href);

        seenIds.add(pid);
        products.push({
            id: 'avito_' + pid,
            avito_id: pid,
            name: title,
            price: price,
            city: city,
            delivery: hasDelivery,
            url: fullUrl
        });
    }
    return products;
}
"""


class AvitoScraper:
    """
    Парсер цен на комплектующие с Авито.
    Использует постоянный профиль Chrome (Persistent Context).
    При появлении проверки на человека приостанавливает выполнение и просит
    пользователя подтвердить сессию в открытом окне браузера.
    """
    def __init__(
        self,
        headless: bool = False,
        proxy: Optional[str] = None,
        profile_dir: Optional[str] = None,
        update_expert_db: bool = True
    ):
        self.headless = headless
        self.proxy = proxy
        self.update_expert_db = update_expert_db
        if profile_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.profile_dir = os.path.join(base_dir, "playwright_avito_profile")
        else:
            self.profile_dir = profile_dir

    async def check_challenge(self, page) -> str:
        """
        Проверяет, требует ли Авито подтверждения:
        - 'ip_block': Авито заблокировало доступ из-за зарубежного IP/VPN.
        - 'captcha': проверка на человека / капча.
        - '': нормальная страница.
        """
        try:
            title = (await page.title()).lower()
            url = page.url.lower()

            # 1. Блокировка по IP (VPN / зарубежный IP)
            if any(w in title for w in ["проблема с ip", "проблем с ip", "доступ ограничен: проблема с ip"]):
                return "ip_block"

            has_ip_block = await page.evaluate("""() => {
                const text = document.body ? document.body.innerText : '';
                return Boolean(
                    text.includes("Страница не загрузилась из-за проблем с IP") ||
                    text.includes("проблема с IP") ||
                    text.includes("Отключить VPN")
                );
            }""")
            if has_ip_block:
                return "ip_block"

            # 2. CAPTCHA / подтверждение человека
            if any(w in title for w in ["доступ ограничен", "проверка", "firewall", "blocked", "captcha"]):
                return "captcha"
            if "firewall" in url or "blocked" in url or "validate" in url:
                return "captcha"

            has_gate = await page.evaluate("""() => {
                const text = document.body ? document.body.innerText : '';
                return Boolean(
                    document.querySelector('.firewall-title, #challenge-form, [class*="firewall"]') ||
                    text.includes("Подтвердите, что вы человек")
                );
            }""")
            if has_gate:
                return "captcha"

            return ""
        except Exception:
            return ""

    def is_valid_item(self, item_name: str, category_key: str, min_price: int = 0, max_price: int = 9999999) -> bool:
        """Фильтрует объявления: отсекает стоп-слова, сломанные комплектующие и выбросы цен."""
        name_lower = item_name.lower()
        cat_info = AVITO_CATEGORIES.get(category_key, {})
        for exc in cat_info.get("exclude", []):
            if exc in name_lower:
                return False
        return True

    def update_expert_component_median(self, target_name: str, median_price: int, comp_type: str = ""):
        """Обновляет среднюю/медианную цену в базе экспертных оценок expert_components."""
        if not median_price or median_price <= 0:
            return
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE expert_components
                    SET price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE componentname = ? OR componentname LIKE ?
                """, (median_price, target_name, f"%{target_name}%"))
                affected = cur.rowcount
                conn.commit()
                if affected > 0:
                    logger.info(f"  [DB] Обновлена экспертная цена '{target_name}': {median_price:,} ₽ (затронуто записей: {affected})")
        except Exception as e:
            logger.error(f"Ошибка обновления expert_components: {e}")

    async def scrape_target_item(self, page, target_item: dict, category_key: str) -> List[Dict[str, Any]]:
        """Парсит конкретную модель (например 'Ryzen 5 5600' или 'RTX 3060')."""
        target_name = target_item["name"]
        query = target_item["query"]
        min_p = target_item.get("min_price", 1000)
        max_p = target_item.get("max_price", 999999)

        # Поиск по России с фильтром минимальной цены для отсева мелочей
        search_url = f"https://www.avito.ru/all?q={query.replace(' ', '+')}&pmin={min_p}&pmax={max_p}&s=101"
        logger.info(f"[{AVITO_CATEGORIES[category_key]['title']}] Поиск: '{query}' ({search_url})")

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            logger.warning(f"Ошибка загрузки страницы для '{query}': {e}")
            return []

        # Проверка на наличие антибот-проверки или блокировки IP
        challenge_type = await self.check_challenge(page)
        if challenge_type == "ip_block":
            logger.error("\n" + "=" * 75)
            logger.error("  [⛔ ОШИБКА AVITO: БЛОКИРОВКА ИЗ-ЗА IP / VPN]")
            logger.error("  Авито заблокировало страницу: «Страница не загрузилась из-за проблем с IP».")
            logger.error("  Причина: активен зарубежный VPN. Авито открывается только с российских IP.")
            logger.error("  Решение:")
            logger.error("   1. Добавьте avito.ru в исключения вашего VPN (Split Tunneling).")
            logger.error("   2. Либо временно отключите VPN на время сбора цен.")
            logger.error("  Скрипт приостановлен (ожидание восстановления связи)...")
            logger.error("=" * 75)
            for _ in range(45):
                await page.wait_for_timeout(2000)
                if not await self.check_challenge(page):
                    logger.info("  [✅] Соединение с Авито восстановлено! Продолжаем сбор...")
                    await page.wait_for_timeout(2000)
                    break
        elif challenge_type == "captcha":
            logger.warning("\n" + "=" * 75)
            logger.warning("  [⚠️] Avito запросило подтверждение пользователя (CAPTCHA).")
            logger.warning("  Пожалуйста, пройдите проверку вручную в открытом окне браузера.")
            logger.warning("  Скрипт ожидает завершения проверки...")
            logger.warning("=" * 75)
            for _ in range(45):
                await page.wait_for_timeout(2000)
                if not await self.check_challenge(page):
                    logger.info("  [✅] Проверка пройдена! Продолжаем сбор данных...")
                    await page.wait_for_timeout(2500)
                    break

        # Прокрутка для подгрузки карточек
        try:
            await page.evaluate("window.scrollBy(0, 1000);")
            await page.wait_for_timeout(random.uniform(1500, 2500))
        except Exception:
            pass

        # Извлечение карточек через DOM
        try:
            raw_cards = await page.evaluate(DOM_EXTRACT_AVITO_JS)
        except Exception as e:
            logger.error(f"Ошибка извлечения товаров DOM: {e}")
            raw_cards = []

        valid_items = []
        prices = []
        for c in raw_cards:
            price = c["price"]
            if not (min_p <= price <= max_p):
                continue
            if not self.is_valid_item(c["name"], category_key):
                continue

            product_record = {
                "id": c["id"],
                "shop": "Авито (Б/У)",
                "name": c["name"],
                "category": category_key,
                "price": price,
                "old_price": None,
                "available": True,
                "url": c["url"],
                "city_id": c.get("city", "Россия"),
                "warranty": "Проверка при покупке",
                "mark": 8,
                "comment": f"Авито (Б/У) | {c.get('city', 'Россия')} | {'Доставка' if c.get('delivery') else 'Самовывоз'}"
            }
            valid_items.append(product_record)
            prices.append(price)

        if prices:
            median_val = int(statistics.median(prices))
            # Округляем до сотен/тысяч
            rounded_median = round(median_val / 500) * 500
            min_found = min(prices)
            logger.info(f"  Найдено {len(valid_items)} объявлений по '{target_name}'. Мин: {min_found:,} ₽, Медиана: {rounded_median:,} ₽")
            if self.update_expert_db:
                self.update_expert_component_median(target_name, rounded_median, category_key)
        else:
            logger.warning(f"  По запросу '{query}' не найдено подходящих объявлений в заданном диапазоне цен.")

        return valid_items

    async def _run_scrape_async(
        self,
        categories: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Асинхронный цикл сбора объявлений по всем компонентам."""
        from playwright.async_api import async_playwright

        target_cats = categories if categories else list(AVITO_CATEGORIES.keys())
        os.makedirs(self.profile_dir, exist_ok=True)

        all_collected: List[Dict[str, Any]] = []

        async with async_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--lang=ru-RU,ru"
            ]

            proxy_settings = None
            if self.proxy:
                proxy_settings = {"server": self.proxy}

            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=self.headless,
                channel="chrome",  # Использует системный Chrome, если доступен
                args=launch_args,
                proxy=proxy_settings,
                permissions=["geolocation"],
                geolocation={"latitude": 55.7558, "longitude": 37.6173},
                viewport={"width": 1366, "height": 820},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                locale="ru-RU",
                timezone_id="Europe/Moscow"
            )

            page = context.pages[0] if context.pages else await context.new_page()

            for cat_key in target_cats:
                cat_info = AVITO_CATEGORIES.get(cat_key)
                if not cat_info:
                    continue

                logger.info(f"\n==========================================")
                logger.info(f"===> Категория: {cat_info['title']} ({cat_key.upper()})")
                logger.info(f"==========================================")

                for target_item in cat_info.get("items", []):
                    items = await self.scrape_target_item(page, target_item, cat_key)
                    all_collected.extend(items)
                    # Случайная пауза между запросами (3-6 сек) для естественного темпа
                    await page.wait_for_timeout(random.uniform(3000, 6000))

            await context.close()

        return all_collected

    def run_scrape_cycle(self, categories: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Точка входа: запускает цикл сбора и сохраняет в SQLite catalog.db."""
        init_db()
        logger.info(f"[*] Запуск парсера цен Авито (Профиль: {self.profile_dir})")
        start_time = time.time()

        collected = asyncio.run(self._run_scrape_async(categories=categories))

        if collected:
            upsert_products(collected)
            logger.info(f"[+] Успешно сохранено {len(collected)} объявлений Авито в SQLite базу catalog.db!")
        else:
            logger.info("[-] Новых объявлений не собрано.")

        duration = time.time() - start_time
        logger.info(f"[*] Цикл сбора Авито завершен за {duration:.1f} сек.")
        return collected


if __name__ == "__main__":
    scraper = AvitoScraper(headless=False)
    scraper.run_scrape_cycle()

