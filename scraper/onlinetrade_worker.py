import os
import re
import time
import random
import logging
from typing import List, Dict, Any, Optional
from db.database import upsert_products, init_db

logger = logging.getLogger("onlinetrade_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ONLINETRADE_CATEGORIES = {
    "psu": {
        "title": "Блоки питания",
        "slug": "bloki_pitaniya-c339"
    },
    "cooler": {
        "title": "Кулеры для процессоров",
        "slug": "kulery_dlya_protsessorov-c338"
    }
}

DOM_EXTRACT_JS = """
() => {
    const products = [];
    const seenIds = new Set();
    
    // Стратегия 1: Поиск по известным контейнерам карточек ОнлайнТрейд
    const cardSelectors = [
        '.indexGoods__item',
        '.catalog__displayedItem',
        '[id^="item_"]',
        '.item__line',
        '.catalogItem'
    ];
    let cards = [];
    for (const sel of cardSelectors) {
        const found = document.querySelectorAll(sel);
        if (found.length > cards.length) {
            cards = Array.from(found);
        }
    }
    
    for (const card of cards) {
        // Ссылка на карточку товара (формат: ...-<id>.html)
        const linkEl = card.querySelector('a[href*="/catalogue/"][href$=".html"]') || 
                       card.querySelector('a[href*="/catalogue/"][href*="item-"]') ||
                       card.querySelector('a[href*="/catalogue/"]');
        if (!linkEl) continue;
        
        const href = linkEl.getAttribute('href') || '';
        const idMatch = href.match(/-(\\d+)\\.html/) || href.match(/item-(\\d+)/) || (card.id && card.id.match(/(\\d+)/));
        const pid = idMatch ? idMatch[1] : null;
        if (!pid || seenIds.has(pid)) continue;
        
        // Название товара (очищаем от лишних символов и кавычек)
        let rawTitle = linkEl.getAttribute('title') || '';
        if (!rawTitle || rawTitle.length < 3) {
            const nameEl = card.querySelector('.indexGoods__item__name, .catalog__displayedItem__name, [class*="name"], [class*="title"], h3, h2');
            rawTitle = nameEl ? nameEl.innerText.trim() : linkEl.innerText.trim();
        }
        let title = rawTitle.replace(/^[\\s"\'«»„“”•\\-\\–\\—]+|[\\s"\'«»„“”]+$/g, '').replace(/\\s+/g, ' ').trim();
        
        // Цена товара: извлекаем ТОЛЬКО первую розничную цену, исключая склеивание со старыми/клубными ценами
        const priceEl = card.querySelector('.price, .regularPrice, [class*="displayedItem__price"], [class*="item__price"], [class*="Price"]');
        let price = null;
        if (priceEl) {
            const priceText = priceEl.innerText || '';
            const matches = Array.from(priceText.matchAll(/([\\d\\s\\xa0]{2,})\\s*(?:₽|руб)?/gi));
            for (const m of matches) {
                const digits = m[1].replace(/\\D/g, '');
                if (digits && digits.length >= 3 && digits.length <= 7) {
                    const parsed = parseInt(digits, 10);
                    if (parsed >= 100 && parsed <= 900000) {
                        price = parsed;
                        break;
                    }
                }
            }
        } else {
            const allText = card.innerText || '';
            const m = allText.match(/([\\d\\s\\xa0]{2,})\\s*(?:₽|руб)/i);
            if (m) {
                const digits = m[1].replace(/\\D/g, '');
                if (digits && digits.length <= 7) price = parseInt(digits, 10);
            }
        }
        
        if (title && title.length >= 3 && price && price > 0 && price <= 900000) {
            seenIds.add(pid);
            products.push({
                id: 'onlinetrade_' + pid,
                name: title,
                price: price,
                url: href.startsWith('http') ? href : 'https://www.onlinetrade.ru' + href
            });
        }
    }
    
    // Стратегия 2: Поиск по всем ссылкам товаров, если классы сетки изменились
    if (products.length === 0) {
        const links = document.querySelectorAll('a[href*="/catalogue/"][href*=".html"]');
        for (const a of links) {
            const href = a.getAttribute('href') || '';
            const m = href.match(/-(\\d+)\\.html/);
            if (!m) continue;
            const pid = m[1];
            if (seenIds.has(pid)) continue;
            
            let parent = a.parentElement;
            let foundPrice = null;
            for (let depth = 0; depth < 5 && parent && parent !== document.body; depth++) {
                const pEl = parent.querySelector('[class*="price"], [class*="Price"]');
                if (pEl) {
                    const priceMatches = Array.from(pEl.innerText.matchAll(/([\\d\\s\\xa0]{2,})\\s*(?:₽|руб)?/gi));
                    for (const pm of priceMatches) {
                        const digits = pm[1].replace(/\\D/g, '');
                        if (digits && digits.length >= 3 && digits.length <= 7) {
                            const val = parseInt(digits, 10);
                            if (val >= 100 && val <= 900000) {
                                foundPrice = val;
                                break;
                            }
                        }
                    }
                    if (foundPrice) break;
                }
                parent = parent.parentElement;
            }
            
            const rawTitle = a.getAttribute('title') || a.innerText.trim();
            const title = rawTitle.replace(/^[\\s"\'«»„“”•\\-\\–\\—]+|[\\s"\'«»„“”]+$/g, '').replace(/\\s+/g, ' ').trim();
            if (title && title.length >= 3 && foundPrice && foundPrice > 0) {
                seenIds.add(pid);
                products.push({
                    id: 'onlinetrade_' + pid,
                    name: title,
                    price: foundPrice,
                    url: href.startsWith('http') ? href : 'https://www.onlinetrade.ru' + href
                });
            }
        }
    }
    
    return products;
}
"""

class OnlineTradeScraper:
    """
    Парсер розничной сети ОнлайнТрейд (onlinetrade.ru).
    Использует нативный Chrome с отключенным флагом автоматизации,
    что предотвращает обнаружение скрипта защитой Servicepipe.
    """
    def __init__(self, headless: bool = False, profile_dir: Optional[str] = None):
        self.headless = headless
        if profile_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.profile_dir = os.path.join(base_dir, "playwright_onlinetrade_profile")
        else:
            self.profile_dir = profile_dir

    async def _wait_for_catalog_or_captcha(self, page, target_url: str, timeout_sec: int = 180) -> bool:
        """
        Ожидание загрузки каталога или решения капчи:
        1. Если виден спиннер проверки — ждет завершения.
        2. Если появилось окно капчи xpvnsulc — терпеливо ждет решения пользователем.
        3. Если каталог открыт — проверяет появление карточек товаров.
        """
        captcha_logged = False
        start_time = time.time()

        while time.time() - start_time < timeout_sec:
            cur_url = page.url
            try:
                content = await page.content()
            except Exception:
                await page.wait_for_timeout(1000)
                continue

            is_captcha = "xpvnsulc" in cur_url or "sp_rotated" in content or "Разверните картинку" in content or "поверните" in content.lower()
            is_spinner = "id_spinner" in content or "spinner-loader" in content

            if is_captcha:
                if not captcha_logged:
                    logger.warning("=" * 65)
                    logger.warning("[!] ОБНАРУЖЕНА ЗАЩИТА SERVICEPIPE (ОНЛАЙНТРЕЙД)")
                    logger.warning("[!] Пожалуйста, поверните ползунок в открывшемся окне браузера!")
                    logger.warning("[!] Скрипт ожидает решения капчи и возврата в каталог...")
                    logger.warning("=" * 65)
                    captcha_logged = True
                    try:
                        import winsound
                        winsound.Beep(1000, 350)
                    except Exception:
                        pass
                await page.wait_for_timeout(2000)
                continue

            if is_spinner:
                await page.wait_for_timeout(1500)
                continue

            # Страница не на капче и не на спиннере: проверяем готовность каталога
            try:
                cards_count = await page.evaluate("""() => {
                    return document.querySelectorAll('.indexGoods__item, .catalog__displayedItem, [id^="item_"], a[href*="/catalogue/"][href$=".html"]').length;
                }""")
            except Exception:
                cards_count = 0

            if cards_count > 0 or len(content) > 25000:
                if captcha_logged:
                    logger.info("[✓] Проверка успешно пройдена! Каталог открыт.")
                await page.wait_for_timeout(1500)
                return True

            await page.wait_for_timeout(1500)

        logger.error(f"[X] Превышено время ожидания загрузки каталога ({timeout_sec} сек).")
        return False

    async def _extract_products_from_page(self, page, category_key: str) -> List[Dict[str, Any]]:
        """Извлекает товары напрямую из DOM страницы Playwright."""
        try:
            raw_items = await page.evaluate(DOM_EXTRACT_JS)
        except Exception as e:
            logger.warning(f"Ошибка выполнения DOM экстрактора: {e}")
            raw_items = []

        products = []
        for itm in raw_items:
            products.append({
                "id": itm["id"],
                "shop": "ОнлайнТрейд",
                "name": itm["name"],
                "category": category_key,
                "price": int(itm["price"]),
                "old_price": None,
                "available": True,
                "url": itm["url"],
                "city_id": "moscow",
                "warranty": "12–36 мес.",
                "mark": 8,
                "comment": "Новый товар из розничной сети ОнлайнТрейд с официальной гарантией."
            })
        return products

    def _parse_html_content(self, html_text: str, category_key: str) -> List[Dict[str, Any]]:
        """Резервный парсер извлечения товаров из сырого HTML."""
        import html as html_lib
        products = []

        pattern = re.compile(
            r'href=["\'](/catalogue/[^"\']+?-(\d+)\.html)["\'][^>]*>(.*?)</a>.*?'
            r'(?:class=["\'][^"\']*price[^"\']*["\'][^>]*>([\d\s\xa0&nbsp;]{2,})\s*(?:₽|руб)?)',
            re.DOTALL | re.IGNORECASE
        )
        for m in pattern.finditer(html_text):
            url, pid, title_raw, price_raw = m.groups()
            cleaned_digits = re.sub(r'\D', '', price_raw)
            if not cleaned_digits or len(cleaned_digits) > 7:
                continue
            clean_price = int(cleaned_digits)
            if clean_price < 100 or clean_price > 900000:
                continue
            raw_title = re.sub(r'<[^>]+>', '', title_raw).strip()
            clean_title = re.sub(r'^[\s"\'«»„“”•\-\–\—]+|[\s"\'«»„“”]+$', '', raw_title).strip()
            if clean_price > 0 and len(clean_title) >= 3:
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

    async def _scrape_all_categories(self, categories: List[str], max_pages: int = 0) -> Dict[str, int]:
        """
        Запускает сессию Google Chrome без флагов автоматизации.
        """
        from playwright.async_api import async_playwright

        stats = {}
        os.makedirs(self.profile_dir, exist_ok=True)

        async with async_playwright() as p:
            # Запускаем настоящий Chrome без --enable-automation
            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="chrome",
                headless=self.headless,
                ignore_default_args=["--enable-automation"],
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                    "--no-sandbox"
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

                    # Ожидаем завершения проверки Servicepipe или решения капчи
                    passed = await self._wait_for_catalog_or_captcha(page, page_url)
                    if not passed:
                        logger.warning(f"Не удалось открыть каталог или пройти капчу для {cat_key}.")
                        break

                    # Извлекаем товары напрямую из DOM
                    page_items = await self._extract_products_from_page(page, cat_key)
                    if not page_items:
                        # Резервная попытка через HTML
                        try:
                            content = await page.content()
                            page_items = self._parse_html_content(content, cat_key)
                        except Exception:
                            pass

                    # Если товаров 0 — ждем 3 секунды для дозагрузки динамического JS
                    if not page_items:
                        logger.info("Ожидание подгрузки товаров (3 сек)...")
                        await page.wait_for_timeout(3000)
                        page_items = await self._extract_products_from_page(page, cat_key)

                    new_items = []
                    for itm in page_items:
                        if itm["id"] not in seen_product_ids:
                            seen_product_ids.add(itm["id"])
                            new_items.append(itm)

                    if not new_items:
                        logger.info(f"[{cat_info['title']}] Товары на странице {current_page} не обнаружены (конец категории).")
                        break

                    category_items_count += len(new_items)
                    upsert_products(new_items)
                    logger.info(f"[{cat_info['title']}] Стр. {current_page}: спарсено {len(new_items)} товаров (Всего в категории: {category_items_count})")

                    # Проверяем наличие следующей страницы (кнопка Следующая ИЛИ ссылки с page > current_page)
                    has_more = await page.evaluate(f"""(curPage) => {{
                        const nextBtn = document.querySelector('.navigation__next, a[title*="Следующая"], .paginator a.next, a.navigation__page_next, .paginator__item_next');
                        if (nextBtn) return true;
                        const pageLinks = Array.from(document.querySelectorAll('a[href*="page="]'));
                        return pageLinks.some(a => {{
                            const m = a.getAttribute('href').match(/page=(\\d+)/);
                            return m && parseInt(m[1], 10) > curPage;
                        }});
                    }}""", current_page)

                    current_page += 1
                    try:
                        await page.evaluate("""async () => {
                            window.scrollBy({ top: 500, behavior: 'smooth' });
                        }""")
                    except Exception:
                        pass

                    # Пауза между страницами
                    between_pages_delay = random.uniform(5.5, 8.5)
                    logger.info(f"Пауза перед следующей страницей: {between_pages_delay:.1f} сек...")
                    try:
                        await page.wait_for_timeout(int(between_pages_delay * 1000))
                    except Exception:
                        logger.info("[!] Окно браузера закрыто. Завершаем сбор категории...")
                stats[cat_key] = category_items_count
                logger.info(f"Завершена категория {cat_info['title']}. Собрано: {category_items_count} позиций.")

                if cat_idx < len(categories) - 1:
                    inter_delay = random.uniform(12.0, 18.0)
                    logger.info(f"Пауза перед следующей категорией: {inter_delay:.1f} сек...")
                    try:
                        await page.wait_for_timeout(int(inter_delay * 1000))
                    except Exception:
                        logger.info("[!] Браузер закрыт. Сбор остановлен.")
                        break

            try:
                await context.close()
            except Exception:
                pass

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
        logger.info(f"Запуск сбора цен ОнлайнТрейд ({len(target_categories)} категорий, режим: {mode_str})...")

        try:
            stats = asyncio.run(self._scrape_all_categories(target_categories, max_pages=max_pages))
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                stats = pool.submit(asyncio.run, self._scrape_all_categories(target_categories, max_pages=max_pages)).result()

        logger.info(f"Цикл сбора ОнлайнТрейд завершён! Итоги: {stats}")
        return stats
