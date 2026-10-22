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
    """Initializes SQLite schema, expert tables, and cleans out old static DNS catalog items."""
    init_db()
    cleanup_static_dns()
    init_expert_tables()

def init_expert_tables():
    """Initializes expert_components and ai_rules tables and seeds them if empty."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Expert used/custom components
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expert_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                componentname TEXT NOT NULL,
                mark INTEGER DEFAULT 8,
                price INTEGER NOT NULL,
                minprice INTEGER,
                comment TEXT,
                analogue TEXT,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_expert_type ON expert_components(type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_expert_price ON expert_components(price);")
        
        # 2. AI learning rules / prompt directives
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                rule_text TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Seed from bot_db.js if expert_components is empty
        cursor.execute("SELECT COUNT(*) FROM expert_components;")
        count = cursor.fetchone()[0]
        if count == 0:
            bot_db_path = os.path.join(PROJECT_ROOT, "bot_db.js")
            if os.path.exists(bot_db_path):
                try:
                    with open(bot_db_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    start_idx = content.find('{')
                    end_idx = content.rfind('};')
                    if start_idx != -1 and end_idx != -1:
                        json_like = content[start_idx:end_idx+1]
                        json_like = re.sub(r'(?m)^(\s*)(\w+)\s*:', r'\1"\2":', json_like)
                        json_like = re.sub(r'(?m)^\s*//.*$', '', json_like)
                        parsed = json.loads(json_like)
                        comps = parsed.get("components", [])
                        for c in comps:
                            cursor.execute("""
                                INSERT INTO expert_components (
                                    type, componentname, mark, price, minprice, comment, analogue, created_by
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'system_bot_db')
                            """, (
                                c.get("type", "other"),
                                c.get("componentname", "Без названия"),
                                c.get("mark", 8),
                                c.get("price", 0),
                                c.get("minprice"),
                                c.get("comment", ""),
                                c.get("analogue", "")
                            ))
                        conn.commit()
                        logger.info(f"Seeded {len(comps)} initial expert components from bot_db.js into SQLite.")
                except Exception as e:
                    logger.error(f"Failed to seed expert components from bot_db.js: {e}")

        conn.commit()

def add_expert_component(data: Dict[str, Any]) -> int:
    """Adds or replaces an expert component identified by type and name."""
    init_expert_tables()
    component_type = data.get("type", "other")
    component_name = data.get("componentname", "Без названия")
    values = (
        component_type,
        component_name,
        data.get("mark", 8),
        int(data.get("price", 0)),
        int(data.get("minprice")) if data.get("minprice") else None,
        data.get("comment", ""),
        data.get("analogue", ""),
        data.get("created_by", ""),
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("""
            SELECT id
            FROM expert_components
            WHERE lower(trim(type)) = lower(trim(?))
              AND lower(trim(componentname)) = lower(trim(?))
            ORDER BY id DESC
        """, (component_type, component_name))
        existing_ids = [row[0] for row in cursor.fetchall()]

        if existing_ids:
            component_id = existing_ids[0]
            cursor.execute("""
                UPDATE expert_components
                SET type = ?, componentname = ?, mark = ?, price = ?, minprice = ?,
                    comment = ?, analogue = ?, created_by = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (*values, component_id))
            if len(existing_ids) > 1:
                duplicate_ids = existing_ids[1:]
                placeholders = ",".join("?" for _ in duplicate_ids)
                cursor.execute(
                    f"DELETE FROM expert_components WHERE id IN ({placeholders})",
                    duplicate_ids,
                )
        else:
            cursor.execute("""
                INSERT INTO expert_components (
                    type, componentname, mark, price, minprice, comment, analogue, created_by, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, values)
            component_id = cursor.lastrowid

        conn.commit()
        return component_id

def get_expert_components(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves the latest entry for each expert component."""
    init_expert_tables()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            WITH ranked_components AS (
                SELECT id, type, componentname, mark, price, minprice, comment,
                       analogue, created_by, created_at, updated_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY lower(trim(type)), lower(trim(componentname))
                           ORDER BY updated_at DESC, id DESC
                       ) AS row_number
                FROM expert_components
            )
            SELECT id, type, componentname, mark, price, minprice, comment,
                   analogue, created_by, created_at
            FROM ranked_components
            WHERE row_number = 1
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def delete_expert_component(comp_id: int) -> bool:
    """Deletes an expert component by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expert_components WHERE id = ?", (comp_id,))
        conn.commit()
        return cursor.rowcount > 0

def add_ai_rule(rule_text: str, title: str = "", created_by: str = "") -> int:
    """Inserts an AI directive/rule."""
    init_expert_tables()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ai_rules (title, rule_text, created_by)
            VALUES (?, ?, ?)
        """, (title or rule_text[:40], rule_text, created_by))
        conn.commit()
        return cursor.lastrowid

def get_ai_rules(active_only: bool = True) -> List[Dict[str, Any]]:
    """Retrieves AI learning rules."""
    init_expert_tables()
    with get_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT id, title, rule_text, is_active, created_by, created_at FROM ai_rules"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY id ASC"
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def delete_ai_rule(rule_id: int) -> bool:
    """Deletes an AI rule by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return cursor.rowcount > 0

def get_stats() -> Dict[str, Any]:
    """Returns database size and breakdown by shops/categories."""
    init_db()
    init_expert_tables()
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        by_shop = dict(conn.execute("SELECT shop, COUNT(*) FROM products GROUP BY shop").fetchall())
        by_cat = dict(conn.execute("SELECT category, COUNT(*) FROM products GROUP BY category").fetchall())
        expert_count = conn.execute("SELECT COUNT(*) FROM expert_components").fetchone()[0]
        rules_count = conn.execute("SELECT COUNT(*) FROM ai_rules WHERE is_active = 1").fetchone()[0]
        return {
            "total_products": total,
            "by_shop": by_shop,
            "by_category": by_cat,
            "expert_components_count": expert_count,
            "ai_rules_count": rules_count
        }
