# -*- coding: utf-8 -*-
"""
Skyrex Dynamic Market Medians Engine.
100% Dynamic Statistical Median Calculator directly from live SQLite database (catalog.db).
NO HARDCODED MEDIANS IN CODE! All medians are calculated from real secondary market listings.
"""

import sqlite3
import re
import statistics
import logging
from typing import Optional, Dict, Any, List, Tuple
from bot_tools.hardware_matcher import extract_chipset, normalize_text

logger = logging.getLogger("dynamic_medians")

JUNK_PATTERNS = [
    r'\bартефакт\b', r'\bартефачит\b', r'\bпод ремонт\b', r'\bна запчаст\b', r'\bнерабоч\b', r'\bне рабоч\b',
    r'\bдефект\b', r'\bс проблемой\b', r'\bс нюансом\b', r'\bполоман\b', r'\bдонор\b',
    r'\bскупка\b', r'skupka', r'\bвыкуп\b', r'vykup', r'с моей доплатой', r'обмен на',
    r'\begpu\b', r'\bthunderbolt\b', r'\bcmp\s*40\b', r'\bcmp40\b', r'\bmi50\b'
]

CPU_BUNDLE_STOPWORDS = [
    "комплект", "komplekt", "combo", "bundle", "материн", "плата", "plata", "motherboard", "мать",
    "b450", "b550", "b650", "b760", "b850", "h610", "a520", "a620", "z790",
    "с кулером", "s kulerom", "с охлажд", "snowman", "vodyanka", "водянка", "bashnya", "башня",
    "сборк", "sbork", "игровой пк", "+", "32gb", "16gb", "ddr5", "ddr4"
]

RAM_JUNK_STOPWORDS = ["sodimm", "so-dimm", "ноут", "ноутбук", "сервер", "ecc", "reg"]


def is_clean_item(name: str, category: str = "") -> bool:
    """Verifies that listing is a working, individual retail/used product and not junk/bundle/repair."""
    nl = name.lower()
    if any(re.search(p, nl) for p in JUNK_PATTERNS):
        return False
    if category == "cpu" and any(b in nl for b in CPU_BUNDLE_STOPWORDS):
        return False
    if category == "ram" and any(w in nl for w in RAM_JUNK_STOPWORDS):
        return False
    return True


def calculate_component_median_from_db(
    query_or_chip: str,
    category: Optional[str] = None,
    db_path: str = "catalog.db",
    conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    """
    Dynamically queries catalog.db (table 'products') for real secondary market (Avito) listings,
    filters out non-working parts, combos and junk, and computes the true statistical median ($P_{50}$).
    
    100% Dynamic - ZERO hardcoded numbers in code!
    """
    if not query_or_chip:
        return None

    close_conn = False
    if conn is None:
        conn = sqlite3.connect(db_path)
        close_conn = True

    try:
        cur = conn.cursor()
        q_lower = query_or_chip.lower().strip()
        cat_filter = f"AND category = '{category.lower().strip()}'" if category else ""

        cur.execute(f"""
            SELECT name, category, price, shop, url 
            FROM products 
            WHERE (shop LIKE '%Авито%' OR url LIKE '%avito%')
              AND price >= 500 AND price <= 500000
              {cat_filter}
        """)
        rows = cur.fetchall()

        matched_prices = []
        matched_items = []

        # 1. Specialized logic for RAM (Generation + Kit Capacity)
        if "ddr5" in q_lower or "ddr4" in q_lower or category == "ram":
            is_ddr5 = "ddr5" in q_lower
            is_32 = any(x in q_lower for x in ["32gb", "32 gb", "32гб", "32 гб", "2x16", "2х16", "2*16"])
            for name, cat, price, shop, url in rows:
                if cat != "ram" and not ("ddr4" in name.lower() or "ddr5" in name.lower()):
                    continue
                if not is_clean_item(name, "ram"):
                    continue
                nl = name.lower()
                item_is_ddr5 = "ddr5" in nl or any(f in nl for f in ["4800", "5200", "5600", "6000", "6400", "7200"])
                if item_is_ddr5 != is_ddr5:
                    continue
                item_is_32 = any(x in nl for x in ["32gb", "32 gb", "32гб", "32 гб", "2x16", "2х16", "2*16"])
                if item_is_32 != is_32:
                    continue
                matched_prices.append(price)
                matched_items.append({"name": name, "price": price, "url": url})

        # 2. Specialized logic for SSD (Capacity: 256GB / 512GB / 1TB / 2TB)
        elif "ssd" in q_lower or category == "ssd" or any(c in q_lower for c in ["1tb", "1 tb", "1тб", "512gb", "512 gb", "256gb"]):
            target_cap = 1000 if any(x in q_lower for x in ["1tb", "1 tb", "1тб", "1000", "960"]) else (
                2000 if any(x in q_lower for x in ["2tb", "2 tb", "2тб", "2000"]) else (
                    256 if any(x in q_lower for x in ["256", "250", "240", "128"]) else 512
                )
            )
            for name, cat, price, shop, url in rows:
                if cat != "ssd":
                    continue
                if not is_clean_item(name, "ssd"):
                    continue
                nl = name.lower()
                item_cap = 1000 if any(x in nl for x in ["1tb", "1 tb", "1тб", "1000", "960"]) else (
                    2000 if any(x in nl for x in ["2tb", "2 tb", "2тб", "2000"]) else (
                        256 if any(x in nl for x in ["256", "250", "240", "128"]) else 512
                    )
                )
                if item_cap == target_cap:
                    matched_prices.append(price)
                    matched_items.append({"name": name, "price": price, "url": url})

        # 3. GPU, CPU, and Motherboards matching via Chipset / Model Token
        else:
            chip = extract_chipset(query_or_chip)
            target_token = chip.lower().replace(" ", "") if chip else q_lower.replace(" ", "")
            is_ti = bool(re.search(r'\b(?:ti|ти)\b', q_lower)) or "ti" in q_lower.replace("super", "")
            is_super = bool(re.search(r'\b(?:super|супер)\b', q_lower))

            for name, cat, price, shop, url in rows:
                if not is_clean_item(name, cat):
                    continue
                nl = name.lower()
                nl_clean = nl.replace(" ", "")
                item_chip = extract_chipset(name)

                matches = False
                if item_chip and chip and item_chip == chip:
                    matches = True
                elif target_token in nl_clean:
                    item_is_ti = bool(re.search(r'\b(?:ti|ти)\b', nl)) or "ti" in nl.replace("super", "")
                    item_is_super = bool(re.search(r'\b(?:super|супер)\b', nl))
                    if is_ti != item_is_ti:
                        continue
                    if is_super != item_is_super and not is_ti:
                        continue
                    matches = True

                if matches:
                    matched_prices.append(price)
                    matched_items.append({"name": name, "price": price, "url": url})

        if not matched_prices:
            return None

        med = int(statistics.median(matched_prices))
        clean_med = int(round(med / 100) * 100)

        return {
            "median": clean_med,
            "raw_median": med,
            "min": min(matched_prices),
            "max": max(matched_prices),
            "count": len(matched_prices),
            "sample_items": matched_items[:5]
        }
    finally:
        if close_conn:
            conn.close()


def sync_all_database_medians(db_path: str = "catalog.db") -> Dict[str, Any]:
    """
    Recalculates all medians purely from live rows in 'products' table (Avito)
    and updates 'expert_components' in catalog.db.
    ZERO hardcoding! 100% dynamic calculation for the dynamic market.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id, type, componentname, price FROM expert_components")
    expert_rows = cur.fetchall()

    updated_count = 0
    results = {}

    for row_id, ctype, cname, old_price in expert_rows:
        res = calculate_component_median_from_db(cname, ctype, conn=conn)
        if res and res["median"] > 0:
            new_price = res["median"]
            comment = f"Динамическая медианная цена ({res['count']} объявлений Авито: {res['min']:,} – {res['max']:,} ₽)"
            cur.execute("""
                UPDATE expert_components 
                SET price = ?, comment = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_price, comment, row_id))
            updated_count += 1
            results[cname] = {
                "old_price": old_price,
                "new_price": new_price,
                "count": res["count"],
                "range": (res["min"], res["max"])
            }

    conn.commit()
    conn.close()
    return {"updated": updated_count, "details": results}
