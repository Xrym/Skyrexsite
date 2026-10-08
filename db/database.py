import sqlite3
import os
import re
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("skyrex_db")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "catalog.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")  # High concurrency
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_db():
    """Initializes tables and FTS5 full-text search indexes."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Main products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                shop TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                price INTEGER NOT NULL,
                old_price INTEGER,
                available BOOLEAN NOT NULL DEFAULT 1,
                url TEXT NOT NULL,
                city_id TEXT NOT NULL DEFAULT 'moscow',
                warranty TEXT,
                mark INTEGER,
                comment TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Indexes for fast category/price/shop filtering
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_price ON products(price);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_shop ON products(shop);")
        
        # 3. FTS5 Virtual Table for sub-millisecond keyword/fuzzy search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
                id UNINDEXED,
                name,
                category,
                shop,
                tokenize='unicode61 remove_diacritics 2'
            );
        """)
        
        conn.commit()
    logger.info(f"Database initialized at {DB_PATH}")

def upsert_products(products: List[Dict[str, Any]]):
    """Inserts or updates a batch of products and keeps FTS5 index in sync."""
    if not products:
        return
        
    with get_connection() as conn:
        cursor = conn.cursor()
        for p in products:
            p_data = {
                "id": p["id"],
                "shop": p.get("shop", "DNS"),
                "name": p["name"],
                "category": p.get("category", "other"),
                "price": int(p["price"]),
                "old_price": int(p["old_price"]) if p.get("old_price") else None,
                "available": 1 if p.get("available", True) else 0,
                "url": p.get("url", ""),
                "city_id": p.get("city_id", "moscow"),
                "warranty": p.get("warranty", "36 мес."),
                "mark": p.get("mark"),
                "comment": p.get("comment", "")
            }
            
            cursor.execute("""
                INSERT INTO products (
                    id, shop, name, category, price, old_price, available, url, city_id, warranty, mark, comment, updated_at
                ) VALUES (
                    :id, :shop, :name, :category, :price, :old_price, :available, :url, :city_id, :warranty, :mark, :comment, CURRENT_TIMESTAMP
                )
                ON CONFLICT(id) DO UPDATE SET
                    price = excluded.price,
                    old_price = excluded.old_price,
                    available = excluded.available,
                    url = excluded.url,
                    warranty = excluded.warranty,
                    mark = excluded.mark,
                    comment = excluded.comment,
                    updated_at = CURRENT_TIMESTAMP;
            """, p_data)
            
            # Keep FTS5 in sync: delete old entry if present, insert new
            cursor.execute("DELETE FROM products_fts WHERE id = ?", (p_data["id"],))
            cursor.execute("""
                INSERT INTO products_fts (id, name, category, shop)
                VALUES (?, ?, ?, ?)
            """, (p_data["id"], p_data["name"], p_data["category"], p_data["shop"]))
            
        conn.commit()

def cleanup_static_dns():
    """Removes previously seeded static DNS catalog items (43 components)."""
    with get_connection() as conn:
        conn.execute("DELETE FROM products WHERE id LIKE 'dns_%';")
        conn.execute("DELETE FROM products_fts WHERE id LIKE 'dns_%';")
        conn.commit()
    logger.info("Removed static DNS components from database.")

def seed_from_bot_db():
    """Initializes SQLite schema and cleans out old static DNS catalog items."""
    init_db()
    cleanup_static_dns()

def get_stats() -> Dict[str, Any]:
    """Returns database size and breakdown by shops/categories."""
    init_db()
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        by_shop = dict(conn.execute("SELECT shop, COUNT(*) FROM products GROUP BY shop").fetchall())
        by_cat = dict(conn.execute("SELECT category, COUNT(*) FROM products GROUP BY category").fetchall())
        return {
            "total_products": total,
            "by_shop": by_shop,
            "by_category": by_cat
        }
