import asyncio
import logging
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from db.database import init_db, upsert_products

logger = logging.getLogger("wildberries_scraper")

WILDBERRIES_CATEGORIES = {
    "gpu": {
        "title": "Видеокарты",
        "query": "видеокарта",
        "relevance": re.compile(r"\bвидеокарт\w*\b", re.I),
        "exclude": re.compile(
            r"\b(?:кабель|переходник|адаптер|подставк\w*|кронштейн|"
            r"держател\w*|охлажден\w*|кулер\w*|чехол|сумк\w*)\s+"
            r"(?:для|к|под)\s+(?:видеокарт\w*|gpu|графическ\w*)\b",
            re.I,
        ),
    },
    "cpu": {
        "title": "Процессоры",
        "query": "процессор",
        "relevance": re.compile(r"\bпроцессор\w*\b", re.I),
        "exclude": re.compile(
            r"\b(?:кулер\w*|охлажден\w*|креплен\w*|рамк\w*|"
            r"держател\w*|термопаст\w*)\s+(?:для|к|под)\s+"
            r"(?:процессор\w*|cpu)\b",
            re.I,
        ),
    },
    "motherboard": {
        "title": "Материнские платы",
        "query": "материнская плата",
        "relevance": re.compile(r"\b(?:материнск\w*|motherboard)\b", re.I),
        "exclude": re.compile(
            r"\b(?:кабель|переходник|адаптер|батаре\w*|креплен\w*|"
            r"держател\w*|заглушк\w*|радиатор\w*)\s+(?:для|к|под)\s+"
            r"(?:материнск\w*|motherboard)\b",
            re.I,
        ),
    },
    "ram": {
        "title": "Оперативная память",
        "query": "оперативная память для компьютера",
        "relevance": re.compile(
            r"\b(?:оперативн\w*\s+памят\w*|модул\w*\s+памят\w*|dimm|so[\s-]?dimm)\b",
            re.I,
        ),
        "exclude": re.compile(
            r"\b(?:радиатор\w*|охлажден\w*|кулер\w*|наклейк\w*|"
            r"накладк\w*|креплен\w*|держател\w*)\s+(?:для|к|под)\s+"
            r"(?:оперативн\w*|памят\w*|ram)\b",
            re.I,
        ),
    },
    "ssd": {
        "title": "SSD накопители",
        "query": "ssd накопитель",
        "relevance": re.compile(r"\b(?:ssd|nvme|m\.?2|твердотельн\w*|накопител\w*)\b", re.I),
        "exclude": re.compile(
            r"\b(?:корпус|бокс|адаптер|кабель|контейнер|переходник)\s+"
            r"(?:для|под)\s+(?:ssd|nvme|m\.?2|накопител\w*)\b",
            re.I,
        ),
    },
    "psu": {
        "title": "Блоки питания",
        "query": "блок питания для компьютера",
        "relevance": re.compile(r"\b(?:блок\w*\s+питан\w*|бп\b|psu|power\s+supply)\b", re.I),
        "exclude": re.compile(
            r"\b(?:кабель|переходник|адаптер|удлинител\w*|держател\w*)\s+"
            r"(?:для|к|под)\s+(?:блок\w*\s+питан\w*|psu|бп)\b",
            re.I,
        ),
    },
    "cooler": {
        "title": "Кулеры для процессоров",
        "query": "кулер для процессора",
        "relevance": re.compile(r"\b(?:кулер\w*|охлажден\w*|сжо|водян\w*)\b", re.I),
        "exclude": re.compile(
            r"\b(?:подставк\w*|креплен\w*|кронштейн|держател\w*|"
            r"термопаст\w*)\s+(?:для|к|под)\s+(?:кулер\w*|процессор\w*|cpu)\b",
            re.I,
        ),
    },
    "case": {
        "title": "Корпуса",
        "query": "корпус для компьютера",
        "relevance": re.compile(r"\b(?:корпус\w*|pc\s+case)\b", re.I),
        "exclude": re.compile(
            r"\bкорпус\w*\s+(?:для|под)\s+(?:ssd|m\.?2|накопител\w*)\b",
            re.I,
        ),
    },
}

_PRODUCT_ID_RE = re.compile(r"/catalog/(\d{5,12})(?:/|$)", re.I)
_PRICE_RE = re.compile(
    r"(?<!\d)(\d(?:[\d \u00a0\u202f]{0,10}\d)?)\s*(?:₽|руб(?:\.|лей)?|р\.)",
    re.I,
)
_PLAIN_PRICE_RE = re.compile(r"(?<!\d)(\d[\d \u00a0\u202f]{1,10}\d)(?!\d)")
_INVALID_PRODUCT_RE = re.compile(
    r"\b(?:б\s*/\s*у|б\.у\.|used|восстановлен\w*|витринн\w*|на\s+запчасти|муляж)\b",
    re.I,
)
_EXCLUDED_PRICE_CLASSES = (
    "upper-price",
    "old-price",
    "price-old",
    "price__old",
    "installment",
    "credit",
)
_CURRENT_PRICE_CLASSES = (
    "price__lower-price",
    "price-current",
    "price__current",
    "price__value",
)
_TITLE_CLASSES = (
    "product-card__name",
    "product-card__title",
    "card__name",
    "product-name",
    "product__name",
)
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


class _HtmlNode:
    def __init__(self, tag: str, attrs: Dict[str, Optional[str]]):
        self.tag = tag
        self.attrs = attrs
        self.children: List[Any] = []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _HtmlNode):
                yield from child.walk()

    def text(self) -> str:
        return "".join(
            child.text() if isinstance(child, _HtmlNode) else child
            for child in self.children
        )


class _ProductHtmlParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _HtmlNode("document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs):
        node = _HtmlNode(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs):
        self.stack[-1].children.append(_HtmlNode(tag, dict(attrs)))

    def handle_endtag(self, tag: str):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str):
        self.stack[-1].children.append(data)


def _classes(node: _HtmlNode) -> set:
    return set((node.attrs.get("class") or "").lower().split())


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _valid_price(value: str) -> Optional[int]:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    price = int(digits)
    return price if 100 <= price <= 20_000_000 else None


def _read_price(node: _HtmlNode, allow_plain: bool = False) -> Optional[int]:
    for attr in ("data-price", "content"):
        value = node.attrs.get(attr)
        if value and value.isdigit():
            price = _valid_price(value)
            if price:
                return price

    text = _normalized_text(node.text())
    match = _PRICE_RE.search(text)
    if match:
        return _valid_price(match.group(1))
    if allow_plain:
        match = _PLAIN_PRICE_RE.search(text)
        if match:
            return _valid_price(match.group(1))
    return None


def _get_product_id(card: _HtmlNode) -> Optional[str]:
    for node in card.walk():
        for attr in ("data-nm-id", "data-product-id"):
            value = node.attrs.get(attr)
            if value and value.isdigit() and 10000 <= int(value) <= 999_999_999_999:
                return value
        href = node.attrs.get("href") or ""
        match = _PRODUCT_ID_RE.search(href)
        if match:
            return match.group(1)
    return None


def _get_title(card: _HtmlNode) -> str:
    for node in card.walk():
        node_classes = _classes(node)
        itemprop = (node.attrs.get("itemprop") or "").lower()
        if itemprop == "name" or any(
            class_name in node_classes for class_name in _TITLE_CLASSES
        ):
            title = _normalized_text(node.text())
            if len(title) >= 3:
                return title

    for node in card.walk():
        if node.tag != "a":
            continue
        for attr in ("data-name", "title", "aria-label"):
            title = _normalized_text(node.attrs.get(attr) or "")
            if len(title) >= 3:
                return title
    return ""


def _get_prices(card: _HtmlNode):
    nodes = list(card.walk())
    for node in nodes:
        node_classes = _classes(node)
        if any(
            current_class in node_classes
            for current_class in _CURRENT_PRICE_CLASSES
        ) or node.tag == "ins" or (node.attrs.get("itemprop") or "").lower() == "price":
            current = _read_price(node, allow_plain=True)
            if current:
                break
    else:
        current = None

    if current is None:
        for node in nodes:
            node_classes = _classes(node)
            if not any("price" in class_name for class_name in node_classes):
                continue
            if any(
                excluded in class_name
                for class_name in node_classes
                for excluded in _EXCLUDED_PRICE_CLASSES
            ):
                continue
            descendants = list(node.walk())[1:]
            if any(
                any(
                    excluded in class_name
                    for excluded in _EXCLUDED_PRICE_CLASSES
                )
                for child in descendants
                for class_name in _classes(child)
            ):
                continue
            current = _read_price(node)
            if current:
                break

    old_price = None
    for node in nodes:
        node_classes = _classes(node)
        if node.tag == "del" or any(
            excluded in class_name
            for class_name in node_classes
            for excluded in _EXCLUDED_PRICE_CLASSES
        ):
            old_price = _read_price(node)
            if old_price:
                break

    if old_price is not None and current is not None and old_price <= current:
        old_price = None
    return current, old_price


def parse_wildberries_html(html: str, category_key: str) -> List[Dict[str, Any]]:
    """Извлекает и проверяет карточки товаров со страницы выдачи Wildberries."""
    if category_key not in WILDBERRIES_CATEGORIES:
        raise ValueError(f"Неизвестная категория Wildberries: {category_key}")

    parser = _ProductHtmlParser()
    parser.feed(html)
    category = WILDBERRIES_CATEGORIES[category_key]
    products = []
    seen_ids = set()

    for card in parser.root.walk():
        card_classes = _classes(card)
        if not (
            card.attrs.get("data-nm-id")
            or card.attrs.get("data-product-id")
            or any(class_name.startswith("product-card") for class_name in card_classes)
        ):
            continue

        product_id = _get_product_id(card)
        if not product_id or product_id in seen_ids:
            continue

        title = _get_title(card)
        if (
            not title
            or not category["relevance"].search(title)
            or category["exclude"].search(title)
            or _INVALID_PRODUCT_RE.search(title)
        ):
            continue

        price, old_price = _get_prices(card)
        if price is None:
            continue

        seen_ids.add(product_id)
        products.append({
            "id": f"wildberries_{product_id}",
            "shop": "Wildberries",
            "name": title,
            "category": category_key,
            "price": price,
            "old_price": old_price,
            "available": True,
            "url": f"https://www.wildberries.ru/catalog/{product_id}/detail.aspx",
            "city_id": "moscow",
            "warranty": None,
            "mark": None,
            "comment": (
                "Цена в карточке Wildberries; доступность и итоговая скидка "
                "могут зависеть от региона и условий покупателя."
            ),
        })
    return products


class WildberriesScraper:
    """Собирает видимые карточки Wildberries без обхода ограничений доступа."""

    def __init__(self, headless: bool = False):
        self.headless = headless

    async def _scrape_categories(
        self, categories: List[str], max_pages: int
    ) -> Dict[str, int]:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright

        stats: Dict[str, int] = {}
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                channel="chrome",
                headless=self.headless,
            )
            try:
                page = await browser.new_page(locale="ru-RU")
                for category_index, category_key in enumerate(categories):
                    category = WILDBERRIES_CATEGORIES.get(category_key)
                    if category is None:
                        raise ValueError(
                            f"Неизвестная категория Wildberries: {category_key}"
                        )

                    seen_ids = set()
                    category_count = 0
                    page_number = 1
                    logger.info(
                        "Начат сбор Wildberries: категория %s (%s)",
                        category["title"],
                        category_key,
                    )

                    while max_pages <= 0 or page_number <= max_pages:
                        url = "https://www.wildberries.ru/catalog/0/search.aspx?" + urlencode({
                            "search": category["query"],
                            "page": page_number,
                        })
                        response = await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=45000,
                        )
                        if response and response.status in (403, 429, 498):
                            raise RuntimeError(
                                f"Wildberries отклонил запрос (HTTP {response.status}); "
                                "сбор остановлен без повторов и обхода ограничения."
                            )

                        try:
                            await page.wait_for_selector(
                                "article.product-card, [data-nm-id], .product-card",
                                timeout=12000,
                            )
                        except PlaywrightTimeoutError:
                            pass

                        body_text = _normalized_text(
                            await page.locator("body").inner_text()
                        ).lower()
                        if any(phrase in body_text for phrase in (
                            "проверяем браузер",
                            "проверка браузера",
                            "подтвердите, что вы не робот",
                        )):
                            raise RuntimeError(
                                "Wildberries показал страницу проверки браузера; "
                                "сбор остановлен без попытки обхода."
                            )

                        items = parse_wildberries_html(
                            await page.content(),
                            category_key,
                        )
                        new_items = [
                            item for item in items
                            if item["id"] not in seen_ids
                        ]
                        if not new_items:
                            logger.info(
                                "На странице Wildberries %s не найдено новых "
                                "подходящих товаров категории %s; пагинация остановлена.",
                                page_number,
                                category_key,
                            )
                            break

                        seen_ids.update(item["id"] for item in new_items)
                        upsert_products(new_items)
                        category_count += len(new_items)
                        logger.info(
                            "Wildberries, категория %s, страница %s: сохранено товаров: %s",
                            category_key,
                            page_number,
                            len(new_items),
                        )
                        page_number += 1
                        await asyncio.sleep(3)

                    stats[category_key] = category_count
                    if category_index < len(categories) - 1:
                        await asyncio.sleep(5)
            finally:
                await browser.close()

        return stats

    def run_scrape_cycle(
        self,
        categories: Optional[List[str]] = None,
        max_pages: int = 1,
    ) -> Dict[str, int]:
        if max_pages < 0:
            raise ValueError("Число страниц должно быть неотрицательным")
        init_db()
        target_categories = categories or list(WILDBERRIES_CATEGORIES)
        logger.info(
            "Запуск сбора Wildberries: категорий %s, страниц максимум: %s",
            len(target_categories),
            max_pages if max_pages else "all",
        )
        try:
            stats = asyncio.run(
                self._scrape_categories(target_categories, max_pages)
            )
        except RuntimeError as error:
            if "asyncio.run() cannot be called" not in str(error):
                raise
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                stats = pool.submit(
                    asyncio.run,
                    self._scrape_categories(target_categories, max_pages),
                ).result()

        logger.info("Сбор Wildberries завершён: %s", stats)
        return stats
