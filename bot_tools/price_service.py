import re
from typing import List, Dict, Any, Optional
from db.database import get_connection, seed_from_bot_db

# Ensure database is seeded on first load
seed_from_bot_db()

def search_price(
    query: str,
    category: Optional[str] = None,
    shop: Optional[str] = None,
    max_price: Optional[int] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Высокоскоростной поиск по базе актуальных цен ОнлайнТрейд, Ситилинк и ДНС с использованием SQLite FTS5.
    Поддерживает полнотекстовый поиск, префиксное сопоставление (4060*), ранжирование BM25 и LIKE fallback.
    """
    clean_query = re.sub(r'[^\w\s]', ' ', query).strip()
    if not clean_query:
        return []

    words = [w for w in clean_query.split() if len(w) >= 1]
    # Prepare FTS expression with prefix wildcard: "RTX 4060" -> "RTX* 4060*"
    fts_expr = " AND ".join([f'"{w}"*' for w in words])

    results = []

    norm_shop = None
    if shop:
        s_low = shop.strip().lower()
        if "онлайн" in s_low or "onlinetrade" in s_low or "трейд" in s_low:
            norm_shop = "ОнлайнТрейд"
        elif "ситилинк" in s_low or "citilink" in s_low:
            norm_shop = "Ситилинк"
        elif "dns" in s_low or "днс" in s_low:
            norm_shop = "DNS"
        else:
            norm_shop = shop.strip()

    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Полнотекстовый поиск FTS5 (BM25 ranking)
        try:
            sql = """
                SELECT p.id, p.name, p.shop, p.price, p.old_price, p.available, p.url,
                       p.category, p.warranty, p.mark, p.comment, p.updated_at
                FROM products_fts fts
                JOIN products p ON fts.id = p.id
                WHERE products_fts MATCH ?
            """
            params = [fts_expr]

            if category:
                sql += " AND p.category = ?"
                params.append(category.lower())

            if norm_shop:
                sql += " AND (p.shop = ? OR LOWER(p.shop) = LOWER(?))"
                params.extend([norm_shop, norm_shop])

            if max_price:
                sql += " AND p.price <= ?"
                params.append(max_price)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            results = [dict(r) for r in rows]
        except Exception:
            results = []

        # 2. Fallback: если FTS5 не нашел совпадений, используем гибкий LIKE
        if not results:
            like_pattern = "%" + "%".join(words) + "%"
            sql_like = """
                SELECT id, name, shop, price, old_price, available, url, category, warranty, mark, comment, updated_at
                FROM products
                WHERE name LIKE ?
            """
            params_like = [like_pattern]

            if category:
                sql_like += " AND category = ?"
                params_like.append(category.lower())

            if norm_shop:
                sql_like += " AND (shop = ? OR LOWER(shop) = LOWER(?))"
                params_like.extend([norm_shop, norm_shop])

            if max_price:
                sql_like += " AND price <= ?"
                params_like.append(max_price)

            sql_like += " ORDER BY price ASC LIMIT ?"
            params_like.append(limit)

            cursor.execute(sql_like, params_like)
            rows_like = cursor.fetchall()
            results = [dict(r) for r in rows_like]

    # Convert available integer to bool
    for item in results:
        item["available"] = bool(item.get("available", 1))

    return results

def format_price_results(results: List[Dict[str, Any]]) -> str:
    """Форматирует найденные товары в красивый HTML блок для чата."""
    if not results:
        return "В базе данных не найдено цен по данному запросу."

    lines = ["🛒 <b>Найдено в каталоге магазинов:</b><br>"]
    for i, item in enumerate(results, 1):
        price_str = f"<b>{item['price']:,} ₽</b>".replace(",", " ")
        old_str = f" <s>{item['old_price']:,} ₽</s>".replace(",", " ") if item.get('old_price') else ""
        link_str = f"<a href='{item['url']}' target='_blank'>{item['name']}</a>"
        shop_tag = f"[{item.get('shop', 'ОнлайнТрейд')}]"
        avail_str = "✅ В наличии" if item.get('available') else "⏳ Под заказ"
        warranty_str = f"Гарантия: {item['warranty']}" if item.get('warranty') else ""

        line = f"{i}. {shop_tag} {link_str} — {price_str}{old_str} ({avail_str})"
        if warranty_str:
            line += f" • <i>{warranty_str}</i>"
        if item.get("comment"):
            line += f"<br>&nbsp;&nbsp;&nbsp;💡 <i>{item['comment']}</i>"
        lines.append(line)

    return "<br>".join(lines)
