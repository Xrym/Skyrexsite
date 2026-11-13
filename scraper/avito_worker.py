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
        "items": [
            {"name": "AMD Radeon RX 580 8GB", "query": "RX 580 8GB"},
            {"name": "NVIDIA GeForce GTX 1660 Super", "query": "GTX 1660 Super"},
            {"name": "AMD Radeon RX 6600", "query": "RX 6600"},
            {"name": "NVIDIA GeForce RTX 2060 Super", "query": "RTX 2060 Super"},
            {"name": "AMD Radeon RX 6600 XT", "query": "RX 6600 XT"},
            {"name": "NVIDIA GeForce RTX 3060 12GB", "query": "RTX 3060 12GB"},
            {"name": "NVIDIA GeForce RTX 3070", "query": "RTX 3070"},
            {"name": "NVIDIA GeForce RTX 4060", "query": "RTX 4060"},
            {"name": "NVIDIA GeForce RTX 5050", "query": "RTX 5050"},
            {"name": "NVIDIA GeForce RTX 5060", "query": "RTX 5060"},
        ],
        "exclude": [
            "ноутбук", "чехол", "райзер", "кабель", "переходник", "подставка", "наклейка",
            "держатель", "коробка", "радиатор", "вентилятор", "кулер", "не рабочий",
            "на запчасти", "артефакт", "донор", "прогретая", "прогрев", "кирпич",
            "ремонт", "скупка", "куплю", "обмен", "аренда"
        ]
    },
    "cpu": {
        "title": "Процессоры",
        "items": [
            {"name": "Intel Core i3-12100F", "query": "i3 12100F"},
            {"name": "AMD Ryzen 5 3600", "query": "Ryzen 5 3600"},
            {"name": "AMD Ryzen 5 5500", "query": "Ryzen 5 5500"},
            {"name": "AMD Ryzen 5 5600", "query": "Ryzen 5 5600"},
            {"name": "Intel Core i5-12400F", "query": "i5 12400F"},
            {"name": "Intel Core i5-13400F", "query": "i5 13400F"},
            {"name": "AMD Ryzen 5 7500F", "query": "Ryzen 5 7500F"},
            {"name": "Intel Core i5-14600KF", "query": "i5 14600KF"},
            {"name": "AMD Ryzen 7 7800X3D", "query": "Ryzen 7 7800X3D"},
        ],
        "exclude": [
            "кулер", "kuler", "башня", "bashnya", "с кулером", "s kulerom", "vodyanka", "водянка",
            "ноутбук", "материнская", "материнка", "мать", "motherboard", "плата", "plata", "mat.plata", "mat plata",
            "комплект", "komplekt", "komlpekt", "combo", "bundle",
            "пк в сборе", "компьютер", "сборка", "sborka", "sborki", "игровой пк", "igrovoy pk", "готовые сборки",
            "коробка", "ножки", "не рабочий", "на запчасти", "донор", "погнуты",
            "b450", "b550", "b650", "b760", "b850", "b840", "h610", "h510", "h410", "a520", "a620", "z790", "z690", "x570", "x670", "x870",
            "+", "snowman", "32gb", "16gb", "ddr5", "ddr4", "ремонт", "скупка", "куплю"
        ]
    },
    "ram": {
        "title": "Оперативная память",
        "items": [
            {"name": "Оперативная память 16 ГБ DDR4", "query": "DDR4 16Gb 2x8"},
            {"name": "Оперативная память DDR4 32 ГБ", "query": "DDR4 32Gb 2x16"},
            {"name": "DDR5 16GB", "query": "DDR5 16Gb"},
            {"name": "Оперативная память DDR5 32GB", "query": "DDR5 32Gb 2x16"},
        ],
        "exclude": ["ноутбук", "sodimm", "so-dimm", "серверная", "ecc", "reg", "чехол", "радиатор", "ремонт", "скупка", "куплю"]
    },
    "motherboard": {
        "title": "Материнские платы",
        "items": [
            {"name": "Материнская плата AM4 A520", "query": "A520 AM4"},
            {"name": "Материнская плата AM4 B550", "query": "B550 AM4"},
            {"name": "Материнская плата LGA 1700 H610", "query": "H610 LGA 1700"},
            {"name": "Материнская плата LGA 1700 B760", "query": "B760 LGA 1700"},
            {"name": "Материнская плата AM5 B650", "query": "B650 AM5"},
        ],
        "exclude": ["ноутбук", "заглушка", "пайка", "процессор", "комплект", "не рабочая", "на запчасти", "донор", "погнут", "ремонт", "скупка", "куплю"]
    },
    "ssd": {
        "title": "SSD накопители",
        "items": [
            {"name": "SSD M.2 NVMe 256GB", "query": "SSD M.2 256Gb"},
            {"name": "SSD M.2 NVMe 512GB", "query": "SSD M.2 512Gb"},
            {"name": "SSD M.2 NVMe 1TB", "query": "SSD M.2 1Tb"},
        ],
        "exclude": ["бокс", "корпус", "радиатор", "переходник", "шлейф", "адаптер", "чехол", "hdd", "жесткий", "ремонт", "скупка", "куплю"]
    }
}


DOM_EXTRACT_AVITO_JS = """
() => {
    const products = [];
    const seenIds = new Set();
    const cards = document.querySelectorAll('[data-marker="item"], div[class*="iva-item-root"]');

    for (const card of cards) {
        // Ссылка на карточку товара
        const linkEl = card.querySelector('a[data-marker="item-title"], [class*="title-root"] a, a[itemprop="url"]');
        if (!linkEl) continue;

        const href = linkEl.getAttribute('href') || '';
        const idMatch = href.match(/_(\\d+)(?:\\?|$)/) || (card.getAttribute('data-item-id') ? [null, card.getAttribute('data-item-id')] : null);
        const pid = idMatch ? idMatch[1] : null;
        if (!pid || seenIds.has(pid)) continue;

        // Извлечение чистого названия товара (избегаем бейджей 'Ещё N фото')
        const titleEl = card.querySelector('h3[itemprop="name"], a[data-marker="item-title"] h3, [class*="title-root"] h3, a[data-marker="item-title"]');
        let title = '';
        if (titleEl) {
            title = titleEl.innerText.trim() || titleEl.getAttribute('title') || '';
        }
        if (!title || title.length < 3 || title.includes('фото') || title.startsWith('Ещё')) {
            title = linkEl.getAttribute('title') || linkEl.innerText.trim();
        }
        if (!title || title.length < 3 || title.includes('фото') || title.startsWith('Ещё')) continue;

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

        # Поиск по всей России без искусственных ценовых рамок
        search_url = f"https://www.avito.ru/all?q={query.replace(' ', '+')}&s=101"
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
            # Санитарный фильтр: отсекаем только фейковые объявления за 1 руб / договорные цены
            if not price or price < 500:
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

