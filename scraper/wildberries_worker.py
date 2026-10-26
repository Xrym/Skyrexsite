import os
import sys
import re
import json
import csv
import time
import random
import logging
import asyncio
from typing import List, Dict, Any, Optional

from db.database import upsert_products, init_db

# Configure logging
logger = logging.getLogger("wildberries_scraper")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

WILDBERRIES_CATEGORIES = {
    "gpu": {
        "title": "Видеокарты",
        "query": "видеокарта",
        "keywords": ["видеокарта", "geforce", "rtx", "gtx", "radeon", "rx", "intel arc"],
        "exclude": ["ноутбук", "чехол", "райзер", "кабель", "переходник", "подставка", "наклейка", "держатель"]
    },
    "motherboard": {
        "title": "Материнские платы",
        "query": "материнская плата",
        "keywords": ["материнская плата", "motherboard", "b550", "b650", "b760", "z790", "a520", "h610", "x670", "am4", "am5", "lga1700"],
        "exclude": ["кабель", "батарейка", "переходник", "планка", "стойка", "заглушка"]
    },
    "ram": {
        "title": "Оперативная память",
        "query": "оперативная память ddr4 ddr5",
        "keywords": ["оперативная память", "ddr4", "ddr5", "ddr3", "dimm", "память"],
        "exclude": ["флешка", "карта памяти", "чехол", "sdhc", "microsd", "картридер"]
    },
    "ssd": {
        "title": "SSD накопители",
        "query": "ssd накопитель m2 nvme",
        "keywords": ["ssd", "накопитель", "m.2", "nvme", "solid state"],
        "exclude": ["чехол", "кабель", "адаптер", "корпус для ssd", "бокс", "переходник", "радиатор"]
    }
}


DOM_EXTRACT_WB_JS = """
() => {
    const products = [];
    const seenIds = new Set();
    const cards = document.querySelectorAll('article.product-card, .j-card-item');
    
    for (const card of cards) {
        let pid = card.getAttribute('data-nm-id') || card.getAttribute('id')?.replace(/\\D/g, '');
        if (!pid) {
            const link = card.querySelector('a.j-card-link, a[href*="/catalog/"]');
            if (link) {
                const m = (link.getAttribute('href') || '').match(/\\/catalog\\/(\\d+)\\//);
                if (m) pid = m[1];
            }
        }
        if (!pid || seenIds.has(pid)) continue;

        // Title: prefer aria-label on primary link, fallback to brand + name
        const linkEl = card.querySelector('a.j-card-link, a[href*="/catalog/"]');
        let title = linkEl ? (linkEl.getAttribute('aria-label') || '').trim() : '';
        
        if (!title) {
            const brandEl = card.querySelector('[class*="brand--"], [class*="brandContainer"], .brand-name');
            const nameEl = card.querySelector('[class*="productName--"], .goods-name');
            const brand = brandEl ? brandEl.innerText.trim() : '';
            const name = nameEl ? nameEl.innerText.trim() : '';
            title = brand ? `${brand} ${name}` : name;
        }
        title = title.replace(/\\s+/g, ' ').trim();
        if (!title || title.length < 3) continue;

        // Current Price
        let price = null;
        let oldPrice = null;
        const insEl = card.querySelector('ins, [class*="mainPriceWrapper"], [class*="lower-price"]');
        if (insEl) {
            const digits = insEl.innerText.replace(/\\D/g, '');
            if (digits) price = parseInt(digits, 10);
        }
        
        // Old / regular Price
        const delEl = card.querySelector('del, [class*="old-price"]');
        if (delEl) {
            const digits = delEl.innerText.replace(/\\D/g, '');
            if (digits) oldPrice = parseInt(digits, 10);
        }
        
        if (!price || price < 100 || price > 3000000) continue;

        // Rating & Reviews count from text
        let rating = 0;
        let feedbacks = 0;
        const cardText = card.innerText || '';
        const rateMatch = cardText.match(/(\\d(?:[,.]\\d)?)\\s*·\\s*(\\d+)\\s*(?:оцен|отзыв)/);
        if (rateMatch) {
            rating = parseFloat(rateMatch[1].replace(',', '.'));
            feedbacks = parseInt(rateMatch[2], 10);
        }

        const url = `https://www.wildberries.ru/catalog/${pid}/detail.aspx`;
        seenIds.add(pid);
        products.push({
            id: 'wb_' + pid,
            wb_id: pid,
            name: title,
            price: price,
            old_price: oldPrice,
            rating: rating,
            feedbacks: feedbacks,
            url: url
        });
    }
    return products;
}
"""


class WildberriesScraper:
    """
    Парсер компьютерных комплектующих с маркетплейса Wildberries.
    Использует нативный экземпляр Google Chrome с сохранением профиля и отключением
    флагов автоматизации для надежного обхода WBAAS / Anti-bot защиты.
    """
    def __init__(
        self,
        headless: bool = False,
        proxy: Optional[str] = None,
        profile_dir: Optional[str] = None,
        min_rating: float = 4.0,
        min_feedbacks: int = 3
    ):
        self.headless = headless
        self.proxy = proxy
        self.min_rating = min_rating
        self.min_feedbacks = min_feedbacks
        if profile_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.profile_dir = os.path.join(base_dir, "playwright_wb_profile")
        else:
            self.profile_dir = profile_dir

    def is_valid_component(
        self,
        title: str,
        category_key: str,
        rating: float = 0.0,
        feedbacks: int = 0
    ) -> bool:
        """Проверяет соответствие названия товара категории, а также пороги рейтинга и отзывов."""
        # 1. Фильтр отзывов и рейтинга (защита от скама, подделок и непроверенных карточек)
        if feedbacks < self.min_feedbacks:
            return False
        if rating < self.min_rating:
            return False

        title_lower = title.lower()
        cat_info = WILDBERRIES_CATEGORIES.get(category_key)
        if not cat_info:
            return True

        # Проверка исключающих стоп-слов
        for exc in cat_info.get("exclude", []):
            if exc in title_lower:
                return False

        # Проверка хотя бы одного целевого ключевого слова
        keywords = cat_info.get("keywords", [])
        if keywords and not any(kw in title_lower for kw in keywords):
            return False

        return True

    async def _scrape_category_pages(
        self,
        page,
        category_key: str,
        max_pages: int = 1
    ) -> List[Dict[str, Any]]:
        """Парсит указанное количество страниц для выбранной категории."""
        cat_info = WILDBERRIES_CATEGORIES[category_key]
        query = cat_info["query"]
        extracted_products: List[Dict[str, Any]] = []
        seen_ids = set()

        for page_num in range(1, max_pages + 1):
            page_param = f"page={page_num}&" if page_num > 1 else ""
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?{page_param}search={query}"
            logger.info(f"[{cat_info['title']}] Страница {page_num}/{max_pages}: {url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"Ошибка загрузки страницы {page_num}: {e}")
                break

            # Небольшая пауза для инициализации и отрисовки страницы
            await page.wait_for_timeout(3500)

            # Проверка на появление экрана подозрительной активности / WBAAS
            body_text = await page.inner_text("body")
            if "Подозрительная активность" in body_text or "Что-то не так..." in body_text:
                logger.warning("=" * 65)
                logger.warning("[!] ОБНАРУЖЕНА ЗАЩИТА WILDBERRIES (WBAAS)")
                logger.warning("[!] Ожидание обновления страницы / прохождения проверки...")
                logger.warning("=" * 65)
                await page.wait_for_timeout(10000)

            # Плавная прокрутка страницы вниз для подгрузки всех 100 товаров (lazy-load)
            await page.evaluate("""async () => {
                const totalHeight = document.body.scrollHeight;
                const distance = 1500;
                for (let scrolled = 0; scrolled < totalHeight; scrolled += distance) {
                    window.scrollBy(0, distance);
                    await new Promise(r => setTimeout(r, 450));
                }
            }""")
            await page.wait_for_timeout(2000)

            # Извлечение товаров через DOM-скрипт
            try:
                raw_items = await page.evaluate(DOM_EXTRACT_WB_JS)
            except Exception as e:
                logger.error(f"Ошибка извлечения товаров из DOM: {e}")
                raw_items = []

            page_added = 0
            for item in raw_items:
                pid = item["wb_id"]
                if pid in seen_ids:
                    continue

                title = item["name"]
                rating = float(item.get("rating") or 0.0)
                feedbacks = int(item.get("feedbacks") or 0)

                if not self.is_valid_component(title, category_key, rating=rating, feedbacks=feedbacks):
                    continue

                seen_ids.add(pid)
                mark_score = min(10, max(1, int(round(rating * 2)))) if rating > 0 else 8

                product_record = {
                    "id": item["id"],
                    "shop": "Wildberries",
                    "name": title,
                    "category": category_key,
                    "price": int(item["price"]),
                    "old_price": int(item["old_price"]) if item.get("old_price") else None,
                    "available": True,
                    "url": item["url"],
                    "city_id": "moscow",
                    "warranty": "12–24 мес.",
                    "mark": mark_score,
                    "rating": rating,
                    "feedback_count": feedbacks,
                    "comment": f"Wildberries | Рейтинг: {rating} ★ | Отзывов: {feedbacks}"
                }
                extracted_products.append(product_record)
                page_added += 1

            logger.info(f"[{cat_info['title']}] Страница {page_num}: найдено {len(raw_items)} карточек, прошло фильтрацию {page_added} комплектующих.")

            if page_added == 0 and page_num > 1:
                logger.info(f"На странице {page_num} нет новых товаров, завершение обхода категории.")
                break

            # Задержка между страницами
            await page.wait_for_timeout(random.uniform(1500, 3000))

        return extracted_products

    async def _run_scrape_async(
        self,
        categories: Optional[List[str]] = None,
        max_pages: int = 1
    ) -> List[Dict[str, Any]]:
        """Асинхронный цикл сбора товаров по категориям."""
        from playwright.async_api import async_playwright

        target_cats = categories if categories else list(WILDBERRIES_CATEGORIES.keys())
        os.makedirs(self.profile_dir, exist_ok=True)

        all_scraped: List[Dict[str, Any]] = []

        async with async_playwright() as p:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--lang=ru-RU,ru"
            ]

            proxy_settings = None
            if self.proxy:
                proxy_settings = {"server": self.proxy}

            context = await p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                channel="chrome",
                headless=self.headless,
                ignore_default_args=["--enable-automation"],
                args=launch_args,
                proxy=proxy_settings,
                viewport={"width": 1440, "height": 900}
            )

            page = context.pages[0] if context.pages else await context.new_page()

            try:
                for idx, cat_key in enumerate(target_cats):
                    if cat_key not in WILDBERRIES_CATEGORIES:
                        logger.warning(f"Категория '{cat_key}' не поддерживается, пропуск.")
                        continue

                    cat_info = WILDBERRIES_CATEGORIES[cat_key]
                    logger.info("=" * 60)
                    logger.info(f"==> НАЧАЛО СБОРА WILDBERRIES [{idx+1}/{len(target_cats)}]: {cat_info['title']} ({cat_key})")
                    logger.info("=" * 60)

                    cat_products = await self._scrape_category_pages(
                        page=page,
                        category_key=cat_key,
                        max_pages=max_pages
                    )
                    all_scraped.extend(cat_products)

                    # Сохранение в SQLite catalog.db после каждой категории
                    if cat_products:
                        upsert_products(cat_products)
                        logger.info(f"[✓] Успешно сохранено {len(cat_products)} товаров в базу catalog.db!")
            finally:
                await context.close()

        return all_scraped

    def run_scrape_cycle(
        self,
        categories: Optional[List[str]] = None,
        max_pages: int = 1,
        export_format: Optional[str] = None,
        export_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Основной метод запуска парсера:
        1. Запускает сбор указанных категорий комплектующих.
        2. Обновляет SQLite базу данных catalog.db.
        3. При необходимости экспортирует результаты в Excel (.xlsx), JSON или CSV.
        """
        init_db()
        logger.info(f"Запуск парсера Wildberries (headless={self.headless}, max_pages={max_pages})")
        
        products = asyncio.run(self._run_scrape_async(categories=categories, max_pages=max_pages))

        logger.info("=" * 60)
        logger.info(f"[✓] Сбор завершен! Всего получено товаров: {len(products)}")
        logger.info("=" * 60)

        # Выгрузка в файл, если запрошено
        if export_path and products:
            fmt = export_format.lower() if export_format else (
                "xlsx" if export_path.endswith(".xlsx") else
                "json" if export_path.endswith(".json") else "csv"
            )

            if fmt in ["xlsx", "excel"]:
                self.export_to_excel(products, export_path)
            elif fmt == "json":
                self.export_to_json(products, export_path)
            elif fmt == "csv":
                self.export_to_csv(products, export_path)

        return products

    @staticmethod
    def export_to_json(products: List[Dict[str, Any]], filepath: str):
        """Экспорт списка товаров в JSON файл с сохранением кодировки UTF-8."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(products, f, ensure_ascii=False, indent=2)
        logger.info(f"[✓] Данные успешно экспортированы в JSON: {filepath} ({len(products)} шт.)")

    @staticmethod
    def export_to_csv(products: List[Dict[str, Any]], filepath: str):
        """Экспорт списка товаров в CSV с BOM (utf-8-sig) для корректного открытия в Excel."""
        if not products:
            return
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        fieldnames = ["id", "shop", "name", "category", "price", "old_price", "url", "mark", "comment"]
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", delimiter=";")
            writer.writeheader()
            for p in products:
                writer.writerow(p)
        logger.info(f"[✓] Данные успешно экспортированы в CSV: {filepath} ({len(products)} шт.)")

    @staticmethod
    def export_to_excel(products: List[Dict[str, Any]], filepath: str):
        """Экспорт списка товаров в форматированный Excel (.xlsx) файл с автошириной колонок."""
        if not products:
            return
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Wildberries Комплектующие"

            headers = [
                "ID товара", "Магазин", "Категория", "Наименование комплектующего",
                "Цена (руб)", "Старая цена", "Рейтинг", "Ссылка на товар", "Примечание"
            ]
            ws.append(headers)

            header_fill = PatternFill(start_color="6C1199", end_color="6C1199", fill_type="solid")
            header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            border_thin = Border(
                left=Side(style='thin', color='DDDDDD'),
                right=Side(style='thin', color='DDDDDD'),
                top=Side(style='thin', color='DDDDDD'),
                bottom=Side(style='thin', color='DDDDDD')
            )

            for col_num in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_num)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")

            for p in products:
                row = [
                    p.get("id"),
                    p.get("shop", "Wildberries"),
                    WILDBERRIES_CATEGORIES.get(p.get("category"), {}).get("title", p.get("category")),
                    p.get("name"),
                    p.get("price"),
                    p.get("old_price"),
                    p.get("mark"),
                    p.get("url"),
                    p.get("comment")
                ]
                ws.append(row)

            # Форматирование ячеек данных и авто-ширина колонок
            for row in ws.iter_rows(min_row=2, max_row=len(products) + 1, min_col=1, max_col=len(headers)):
                for cell in row:
                    cell.border = border_thin
                    if cell.column == 5 or cell.column == 6:
                        cell.number_format = '#,##0 "₽"'
                        cell.alignment = Alignment(horizontal="right")

            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 70)

            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            wb.save(filepath)
            logger.info(f"[✓] Данные успешно экспортированы в Excel: {filepath} ({len(products)} шт.)")
        except ImportError:
            logger.warning("Библиотека openpyxl не найдена, экспорт выполняется в CSV...")
            fallback_csv = filepath.replace(".xlsx", ".csv")
            WildberriesScraper.export_to_csv(products, fallback_csv)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Wildberries PC Components Parser")
    parser.add_argument("--cat", nargs="+", help="Список категорий: gpu cpu motherboard ram ssd psu cooler case")
    parser.add_argument("--pages", type=int, default=1, help="Количество страниц (по 100 товаров)")
    parser.add_argument("--headless", action="store_true", help="Запуск в фоновом режиме без окна браузера")
    parser.add_argument("--min-rating", type=float, default=4.0, help="Минимальный рейтинг товара (по умолчанию: 4.0)")
    parser.add_argument("--min-feedbacks", type=int, default=3, help="Минимальное количество отзывов (по умолчанию: 3)")
    parser.add_argument("--export-excel", type=str, default=None, help="Путь для сохранения в Excel (.xlsx)")
    parser.add_argument("--export-json", type=str, default=None, help="Путь для сохранения в JSON (.json)")
    parser.add_argument("--export-csv", type=str, default=None, help="Путь для сохранения в CSV (.csv)")

    args = parser.parse_args()
    scraper = WildberriesScraper(
        headless=args.headless,
        proxy=args.proxy,
        min_rating=args.min_rating,
        min_feedbacks=args.min_feedbacks
    )

    export_path = args.export_excel or args.export_json or args.export_csv
    export_fmt = "xlsx" if args.export_excel else ("json" if args.export_json else ("csv" if args.export_csv else None))

    scraper.run_scrape_cycle(
        categories=args.cat,
        max_pages=args.pages,
        export_format=export_fmt,
        export_path=export_path
    )
