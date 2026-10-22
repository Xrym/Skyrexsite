import re
import time
import random
import logging
from typing import List, Dict, Any, Optional
from curl_cffi import requests

from db.database import upsert_products, init_db

logger = logging.getLogger("wb_scraper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# -------------------------------------------------------------------------
# КОНФИГУРАЦИЯ КАТЕГОРИЙ, ЗАПРОСОВ И ФИЛЬТРОВ ДЛЯ АДЕКВАТНЫХ КОМПЛЕКТУЮЩИХ
# -------------------------------------------------------------------------

# Глобальные стоп-слова (отсекаем готовые ПК, б/у, рефабы, ноутбучное железо и аксессуары)
GLOBAL_STOP_WORDS = [
    "системный блок", "пк в сборе", "игровой пк", "компьютер в сборе", "готовый пк",
    "ноутбук", "для ноутбука", "sodimm", "so-dimm", "macbook",
    "б/у", "бу ", "восстановленн", "рефаб", "refurbished", "уценен", "витринный",
    "xeon", "зеон", "x79", "x99", "lga2011", "2011-v3", "1356", "1155", "1150", "1151", "ddr3",
    "переходник", "кабель", "удлинитель", "разветвитель", "райзер", "riser", "адаптер",
    "держатель", "подставка", "кронштейн", "рамка", "термопаста", "термопрокладк",
    "чехол", "наклейк", "муляж", "коробка от", "пустая коробка", "брелок", "коврик"
]

WB_CATEGORIES = {
    "gpu": {
        "title": "Видеокарты",
        "queries": [
            "видеокарта rtx 4060", "видеокарта rtx 4060 ti", "видеокарта rtx 4070", 
            "видеокарта rtx 4070 super", "видеокарта rtx 4070 ti super", "видеокарта rtx 4080 super",
            "видеокарта rtx 5070", "видеокарта rtx 5070 ti", "видеокарта rtx 5080",
            "видеокарта rtx 3060", "видеокарта rx 6600", "видеокарта rx 7600", 
            "видеокарта rx 7700 xt", "видеокарта rx 7800 xt"
        ],
        "min_price": 15000,
        "max_price": 350000,
        "must_contain_any": ["rtx", "rx ", "geforce", "radeon", "arc "],
        "stop_words": ["gt 710", "gt 730", "gt 1030", "rx 580", "rx 570", "rx 550", "gtx 1650", "gtx 1050", "gtx 1060", "майнинг", "кулер для видеокарты", "вентилятор для видеокарты"]
    },
    "cpu": {
        "title": "Процессоры",
        "queries": [
            "процессор ryzen 5 5600", "процессор ryzen 5 7500f", "процессор ryzen 5 7600",
            "процессор ryzen 7 5700x", "процессор ryzen 7 5700x3d", "процессор ryzen 7 7700",
            "процессор ryzen 7 7800x3d", "процессор ryzen 7 9800x3d", "процессор ryzen 5 8400f",
            "процессор intel core i3 12100f", "процессор intel core i5 12400f", 
            "процессор intel core i5 13400f", "процессор intel core i5 14400f", 
            "процессор intel core i5 14600kf", "процессор intel core ultra"
        ],
        "min_price": 5500,
        "max_price": 120000,
        "must_contain_any": ["ryzen", "core i3", "core i5", "core i7", "core i9", "core ultra", "процессор"],
        "stop_words": ["кулер", "охлаждение", "рамка", "комплект", "материнская плата", "сокет", "pentium", "celeron", "athlon"]
    },
    "motherboard": {
        "title": "Материнские платы",
        "queries": [
            "материнская плата b550", "материнская плата a520", "материнская плата b650", 
            "материнская плата x670", "материнская плата b850", "материнская плата x870",
            "материнская плата h610", "материнская плата b760", "материнская плата z790",
            "материнская плата z890", "материнская плата b860"
        ],
        "min_price": 4500,
        "max_price": 90000,
        "must_contain_any": ["материнская плата", "b550", "a520", "b450", "b650", "x670", "b850", "x870", "h610", "b660", "b760", "z790", "z890", "b860"],
        "stop_words": ["комплект", "с процессором", "h61", "h81", "h110", "b75", "b85", "a320"]
    },
    "ram": {
        "title": "Оперативная память",
        "queries": [
            "оперативная память ddr4 16gb", "оперативная память ddr4 32gb",
            "оперативная память ddr5 32gb", "оперативная память ddr5 64gb",
            "оперативная память ddr5 6000"
        ],
        "min_price": 2500,
        "max_price": 60000,
        "must_contain_any": ["ddr4", "ddr5"],
        "stop_words": ["ddr3", "4gb", "4 гб", "радиатор для", "серверная", "ecc", "reg "]
    },
    "ssd": {
        "title": "SSD накопители",
        "queries": [
            "ssd m2 nvme 500gb", "ssd m2 nvme 1tb", "ssd m2 nvme 2tb",
            "ssd накопитель samsung", "ssd накопитель kingston", "ssd накопитель adata xpg"
        ],
        "min_price": 2500,
        "max_price": 50000,
        "must_contain_any": ["ssd", "ссд", "nvme", "m.2", "m2", "твердотельный"],
        "stop_words": ["внешний", "карман", "бокс", "корпус для ssd", "радиатор для ssd", "переходник", "адаптер", "120gb", "120 гб", "128gb", "128 гб", "hdd", "жесткий диск", "флешка"]
    },
    "psu": {
        "title": "Блоки питания",
        "queries": [
            "блок питания для пк 650w", "блок питания для пк 750w", "блок питания для пк 850w",
            "блок питания deepcool", "блок питания montech", "блок питания be quiet",
            "блок питания chieftec", "блок питания 1stplayer", "блок питания cougar"
        ],
        "min_price": 3200,
        "max_price": 50000,
        "must_contain_any": ["блок питания", "w ", "вт", "ватт", "psu"],
        "stop_words": ["для ноутбука", "для светодиодной", "для камер", "для роутера", "для монитора", "зарядное устройство", "12в", "12v", "24v", "кабель", "тестер"]
    },
    "cooler": {
        "title": "Кулеры для процессоров",
        "queries": [
            "кулер для процессора id-cooling", "кулер для процессора deepcool",
            "кулер для процессора jonsbo", "кулер для процессора thermalright",
            "система водяного охлаждения для пк", "сжо для процессора"
        ],
        "min_price": 900,
        "max_price": 35000,
        "must_contain_any": ["кулер", "охлажден", "сжо", "водяного", "радиатор"],
        "stop_words": ["для корпуса", "корпусный вентилятор", "набор вентиляторов", "для телефона", "для смартфона", "подставка для ноутбука", "термопаста"]
    },
    "case": {
        "title": "Корпуса",
        "queries": [
            "корпус для пк игровой", "корпус для компьютера atx", "корпус для пк matx",
            "корпус для пк montech", "корпус для пк deepcool", "корпус для пк ardor",
            "корпус для пк 1stplayer", "корпус для пк cougar", "корпус для пк lian li", "корпус для пк jonsbo"
        ],
        "min_price": 2500,
        "max_price": 45000,
        "must_contain_any": ["корпус"],
        "stop_words": ["для жесткого диска", "для ssd", "для hdd", "для флешки", "для наушников", "для ключа", "для телефона", "вентилятор для корпуса", "кулер для корпуса", "пылевой фильтр"]
    }
}

# -------------------------------------------------------------------------
# BLACKLIST СОМНИТЕЛЬНЫХ "НОУНЕЙМ" БРЕНДОВ НА ВБ
# -------------------------------------------------------------------------
BANNED_BRANDS = {
    "huananzhi", "machinist", "atermiter", "kllisre", "jginyue", "mllse", 
    "peladn", "soyoview", "veineda", "jieshuo", "maxsun", "zeuslap", "kingspec",
    "goldenfir", "somnambulist", "walram", "xraydisk", "exegate"
}


class WildberriesScraper:
    """
    Парсер комплектующих для ПК с маркетплейса Wildberries.
    Использует curl_cffi для имитации TLS-отпечатка Chrome и обхода антифрод-защиты WB.
    Содержит строгий фильтр от рефабов, китайских серверных мутантов и нерелевантных аксессуаров.
    """
    def __init__(self, city_id: str = "moscow", dest: str = "-1257786"):
        self.city_id = city_id
        self.dest = dest
        self.headers = {
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.wildberries.ru",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

    def _is_valid_component(self, name: str, brand: str, price: int, rating: float, feedbacks: int, cat_key: str) -> bool:
        cat_cfg = WB_CATEGORIES[cat_key]
        
        if price < cat_cfg["min_price"] or price > cat_cfg["max_price"]:
            return False

        full_text = f"{brand} {name}".lower()
        brand_clean = brand.lower().strip()

        for bad_brand in BANNED_BRANDS:
            if bad_brand in brand_clean or bad_brand in full_text:
                return False

        for stop_word in GLOBAL_STOP_WORDS:
            if stop_word in full_text:
                return False

        for stop_word in cat_cfg.get("stop_words", []):
            if stop_word in full_text:
                return False

        must_words = cat_cfg.get("must_contain_any", [])
        if must_words and not any(w in full_text for w in must_words):
            return False

        if feedbacks >= 3 and rating < 4.2:
            return False

        return True

    def _calculate_mark(self, rating: float, feedbacks: int) -> int:
        if feedbacks >= 20 and rating >= 4.7:
            return 8
        elif feedbacks >= 5 and rating >= 4.5:
            return 7
        elif feedbacks == 0:
            return 6
        return 5

    def _scrape_query(self, session: requests.Session, query: str, cat_key: str, max_pages: int = 2) -> List[Dict[str, Any]]:
        results = []
        url = "https://search.wb.ru/exactmatch/ru/common/v5/search"

        for page in range(1, max_pages + 1):
            params = {
                "ab_testing": "false",
                "appType": "1",
                "curr": "rub",
                "dest": self.dest,
                "page": str(page),
                "query": query,
                "resultset": "catalog",
                "sort": "popular",
                "spp": "30",
                "suppressSpellcheck": "false"
            }

            headers = self.headers.copy()
            headers["Referer"] = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}"

            try:
                resp = session.get(url, headers=headers, params=params, timeout=15)
                if resp.status_code == 429:
                    logger.warning("[!] Код 429 (Too Many Requests) от WB! Пауза 15 секунд...")
                    time.sleep(15)
                    continue
                elif resp.status_code != 200:
                    logger.warning(f"[!] Ошибка HTTP {resp.status_code} для запроса '{query}' (стр. {page})")
                    break

                data = resp.json()
                raw_products = data.get("data", {}).get("products", [])
                if not raw_products:
                    break

                for item in raw_products:
                    pid = item.get("id")
                    if not pid:
                        continue

                    raw_name = item.get("name", "").strip()
                    brand = item.get("brand", "").strip()
                    rating = float(item.get("reviewRating", 0.0))
                    feedbacks = int(item.get("feedbacks", 0))
                    total_qty = int(item.get("totalQuantity", 1))

                    if total_qty <= 0:
                        continue

                    price = 0
                    old_price = None
                    sizes = item.get("sizes", [])
                    if sizes and "price" in sizes[0]:
                        p_info = sizes[0]["price"]
                        price = p_info.get("product", 0) // 100
                        basic = p_info.get("basic", 0) // 100
                        if basic > price:
                            old_price = basic
                    else:
                        price = item.get("salePriceU", 0) // 100
                        basic = item.get("priceU", 0) // 100
                        if basic > price:
                            old_price = basic

                    if not price:
                        continue

                    if not self._is_valid_component(raw_name, brand, price, rating, feedbacks, cat_key):
                        continue

                    if brand and brand.lower() not in raw_name.lower():
                        full_title = f"{brand} {raw_name}"
                    else:
                        full_title = raw_name

                    full_title = re.sub(r'\s+', ' ', full_title).strip()
                    mark = self._calculate_mark(rating, feedbacks)

                    comment_str = (
                        f"Товар с маркетплейса Wildberries. Рейтинг: {rating} ({feedbacks} отз.). "
                        f"Цена без учета доп. скидки WB Кошелька."
                    )

                    results.append({
                        "id": f"wb_{pid}",
                        "shop": "Wildberries",
                        "name": full_title,
                        "category": cat_key,
                        "price": int(price),
                        "old_price": int(old_price) if old_price else None,
                        "available": True,
                        "url": f"https://www.wildberries.ru/catalog/{pid}/detail.aspx",
                        "city_id": self.city_id,
                        "warranty": "По правилам WB / Продавца",
                        "mark": mark,
                        "comment": comment_str
                    })

            except Exception as e:
                logger.warning(f"Ошибка при запросе '{query}' (стр. {page}): {e}")
                break

            time.sleep(random.uniform(1.8, 3.5))

        return results

    def run_scrape_cycle(self, categories: Optional[List[str]] = None, max_pages: int = 2) -> Dict[str, int]:
        init_db()
        target_categories = categories or list(WB_CATEGORIES.keys())
        pages_per_query = 2 if max_pages <= 0 else max_pages

        stats = {}
        logger.info(f"Запуск сбора цен Wildberries ({len(target_categories)} категорий, до {pages_per_query} стр. на запрос)...")

        with requests.Session(impersonate="chrome124") as session:
            for cat_idx, cat_key in enumerate(target_categories):
                if cat_key not in WB_CATEGORIES:
                    continue

                cat_info = WB_CATEGORIES[cat_key]
                queries = cat_info["queries"]

                logger.info("=" * 60)
                logger.info(f"==> СБОР КАТЕГОРИИ WB [{cat_idx+1}/{len(target_categories)}]: {cat_info['title']} ({cat_key})")
                logger.info("=" * 60)

                seen_product_ids = set()
                category_items_count = 0

                for q_idx, query in enumerate(queries):
                    logger.info(f"[{cat_info['title']}] Запрос ({q_idx+1}/{len(queries)}): '{query}'")
                    items = self._scrape_query(session, query, cat_key, max_pages=pages_per_query)

                    new_items = []
                    for itm in items:
                        if itm["id"] not in seen_product_ids:
                            seen_product_ids.add(itm["id"])
                            new_items.append(itm)

                    if new_items:
                        upsert_products(new_items)
                        category_items_count += len(new_items)
                        logger.info(f"  -> Добавлено в БД: {len(new_items)} качественных позиций (Всего в категории: {category_items_count})")
                    else:
                        logger.info("  -> Новых подходящих позиций не найдено.")

                    time.sleep(random.uniform(2.0, 4.0))

                stats[cat_key] = category_items_count
                logger.info(f"Завершена категория {cat_info['title']}. Итого собрано: {category_items_count} шт.")

                if cat_idx < len(target_categories) - 1:
                    inter_delay = random.uniform(5.0, 8.0)
                    logger.info(f"Пауза перед следующей категорией: {inter_delay:.1f} сек...")
                    time.sleep(inter_delay)

        logger.info(f"Цикл сбора Wildberries завершён! Итоги: {stats}")
        return stats


if __name__ == "__main__":
    scraper = WildberriesScraper(city_id="moscow")
    scraper.run_scrape_cycle(max_pages=2)
