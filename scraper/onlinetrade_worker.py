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
    def __init__(self, headless: bool = False, profile_dir: Optional[str] = None):
        # Default headless=False allows the user to solve the Servicepipe captcha in the opened window.
        # Once solved, cookies and session are stored in persistent profile_dir.
        self.headless = headless
        if profile_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.profile_dir = os.path.join(base_dir, "playwright_onlinetrade_profile")
        else:
            self.profile_dir = profile_dir

    async def _handle_captcha_if_needed(self, page, target_url: str) -> bool:
        """
        Проверяет, появилось ли окно проверки или капчи Servicepipe (xpvnsulc / sp_rotated).
        Если появилось, терпеливо ждёт, пока пользователь повернёт ползунок
        И страница реально вернется в каталог товаров (url содержит /catalogue/).
        """
        cur_url = page.url
        try:
            content = await page.content()
        except Exception:
            content = ""

        is_challenge = "xpvnsulc" in cur_url or "sp_rotated" in content or "Разверните картинку" in content or "проверку" in content

        if not is_challenge:
            return True

        logger.warning("=" * 65)
        logger.warning("[!] ОБНАРУЖЕНА ЗАЩИТА SERVICEPIPE (ОНЛАЙНТРЕЙД)")
        logger.warning("[!] Пожалуйста, поверните ползунок в открывшемся окне браузера!")
        logger.warning("[!] Скрипт ожидает прохождения капчи и перехода в каталог товаров...")
        logger.warning("=" * 65)

        # Ждем до 120 секунд, пока URL вернется в нормальный каталог
        for sec in range(60):
            await page.wait_for_timeout(2000)
            cur_url = page.url
            try:
                cur_content = await page.content()
            except Exception:
                cur_content = ""

            # Условие успеха: мы больше не на странице капчи, а вернулись в каталог
            if "xpvnsulc" not in cur_url and ("catalogue" in cur_url or "indexGoods__item" in cur_content or "catalog__displayedItem" in cur_content):
                logger.info("[✓] Капча успешно пройдена! Каталог открыт.")
                # Даем 3 секунды подгрузиться компонентам
                await page.wait_for_timeout(3000)
                return True

        logger.error("[X] Время ожидания капчи истекло (2 минуты).")
        return False

    async def _scrape_all_categories(self, categories: List[str], max_pages: int = 0) -> Dict[str, int]:
        """
        Запускает единую браузерную сессию для всех категорий,
        чтобы капчу нужно было решить максимум один раз в начале.
        """
        from playwright.async_api import async_playwright

        stats = {}
        os.makedirs(self.profile_dir, exist_ok=True)

        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="chrome",
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ],
                viewport=None
            )
            page = context.pages[0] if context.pages else await context.new_page()

            for cat_idx, cat_key in enumerate(categories):
                if cat_key not in ONLINETRADE_CATEGORIES:
                    continue

                cat_info = ONLINETRADE_CATEGORIES[cat_key]
                base_slug = cat_info['slug']
                logger.info("=" * 60)
                logger.info(f"==> НАЧАЛО СБОРА КАТЕГОРИИ [{cat_idx+1}/{len(categories)}]: {cat_info['title']} ({cat_key})")
                logger.info("=" * 60)

                seen_product_ids = set()
                category_items_count = 0
                current_page = 1

                while True:
                    if max_pages > 0 and current_page > max_pages:
                        logger.info(f"Достигнут лимит страниц ({max_pages}) для категории {cat_key}.")
                        break

                    page_url = (
                        f"https://www.onlinetrade.ru/catalogue/{base_slug}/"
                        if current_page == 1
                        else f"https://www.onlinetrade.ru/catalogue/{base_slug}/?page={current_page}"
                    )

                    logger.info(f"[{cat_info['title']}] Запрос страницы {current_page}: {page_url}")
                    try:
                        await page.goto(page_url, wait_until="domcontentloaded", timeout=45000)
                    except Exception as e:
                        logger.warning(f"Ошибка перехода на страницу {current_page}: {e}")
                        break

                    # Пауза на выполнение скриптов
                    sleep_time = random.uniform(3.5, 5.0)
                    await page.wait_for_timeout(int(sleep_time * 1000))

                    # Проверяем и ждем решения капчи
                    passed = await self._handle_captcha_if_needed(page, page_url)
                    if not passed:
                        logger.warning(f"Не удалось пройти капчу на категории {cat_key}.")
                        break

                    try:
                        content = await page.content()
                    except Exception:
                        await page.wait_for_timeout(2000)
                        content = await page.content()

                    page_items = self._parse_html_content(content, cat_key)

                    new_items = []
                    for itm in page_items:
                        if itm["id"] not in seen_product_ids:
                            seen_product_ids.add(itm["id"])
                            new_items.append(itm)

                    if not new_items:
                        logger.info(f"[{cat_info['title']}] Товары на странице {current_page} закончились (Конец категории).")
                        break

                    category_items_count += len(new_items)
                    # Сразу сохраняем товары в SQLite базу
                    upsert_products(new_items)
                    logger.info(f"[{cat_info['title']}] Стр. {current_page}: спарсено {len(new_items)} товаров (Всего в категории: {category_items_count})")

                    # Проверяем наличие следующей страницы
                    next_button = await page.query_selector('.navigation__next, a[title*="Следующая"], .paginator a.next')
                    if not next_button and current_page > 1:
                        logger.info(f"[{cat_info['title']}] Последняя страница категории достигнута.")
                        break

                    current_page += 1
                    between_pages_delay = random.uniform(2.5, 4.0)
                    await page.wait_for_timeout(int(between_pages_delay * 1000))

                stats[cat_key] = category_items_count
                logger.info(f"Завершена категория {cat_info['title']}. Собрано: {category_items_count} позиций.")

                # Пауза перед следующей категорией
                if cat_idx < len(categories) - 1:
                    inter_delay = random.uniform(8.0, 14.0)
                    logger.info(f"Пауза перед следующей категорией: {inter_delay:.1f} сек...")
                    await page.wait_for_timeout(int(inter_delay * 1000))

            await context.close()

        return stats

    def run_scrape_cycle(self, categories: Optional[List[str]] = None, max_pages: int = 0) -> Dict[str, int]:
        """
        Запускает полный цикл сбора по всем категориям в рамках единой сессии Chrome.
        max_pages=0 парсит ВСЕ страницы до конца каталога.
        """
        import asyncio
        init_db()
        target_categories = categories or list(ONLINETRADE_CATEGORIES.keys())

        mode_str = f"ВСЕ страницы (до конца каталога)" if max_pages == 0 else f"до {max_pages} страниц"
        logger.info(f"Запуск полного сбора цен ОнлайнТрейд ({len(target_categories)} категорий, режим: {mode_str})...")

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    stats = pool.submit(asyncio.run, self._scrape_all_categories(target_categories, max_pages=max_pages)).result()
            else:
                stats = asyncio.run(self._scrape_all_categories(target_categories, max_pages=max_pages))
        except Exception as e:
            logger.error(f"Ошибка в цикле сбора: {e}")
            stats = asyncio.run(self._scrape_all_categories(target_categories, max_pages=max_pages))

        logger.info(f"Полный цикл сбора ОнлайнТрейд успешно завершён! Итоги: {stats}")
        return stats
