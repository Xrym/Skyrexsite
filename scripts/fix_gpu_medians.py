# -*- coding: utf-8 -*-
"""
Skyrex Database Hygiene & Dynamic Median Synchronization.
Purges invalid/broken listings and synchronizes reference medians dynamically from live products.
ZERO HARDCODED PRICES IN CODE!
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3
import re
from bot_tools.dynamic_medians import sync_all_database_medians, JUNK_PATTERNS

def apply_fixes(db_path="catalog.db"):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # 1. Purge junk, broken, buyback and egpu listings from products
    cur.execute("SELECT id, name FROM products WHERE category = 'gpu'")
    gpu_rows = cur.fetchall()
    deleted_junk = 0
    for pid, name in gpu_rows:
        nl = name.lower()
        if any(re.search(p, nl) for p in JUNK_PATTERNS):
            cur.execute("DELETE FROM products WHERE id = ?", (pid,))
            cur.execute("DELETE FROM products_fts WHERE id = ?", (pid,))
            deleted_junk += 1
    con.commit()
    con.close()
    print(f"[✓] Purged {deleted_junk} junk/broken/eGPU products from {db_path}.")

    # 2. Recalculate dynamic medians from live products table
    res = sync_all_database_medians(db_path)
    print(f"[✓] Successfully recalculated {res['updated']} component medians dynamically from database.")

if __name__ == "__main__":
    apply_fixes()
