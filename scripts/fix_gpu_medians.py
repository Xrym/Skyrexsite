import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import sqlite3
import re
from bot_tools.hardware_matcher import extract_chipset, match_expert_assessment, resolve_avito_median_price

GPU_MEDIANS = [
    # AMD
    ("AMD Radeon RX 580 8GB", "gpu", 5500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 5600 XT", "gpu", 11500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 5700 XT", "gpu", 14500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 6600", "gpu", 16500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 6600 XT", "gpu", 20000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 6700 XT", "gpu", 26000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 6800 XT", "gpu", 34000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 7600", "gpu", 22000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 7700 XT", "gpu", 38000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("AMD Radeon RX 7800 XT", "gpu", 46000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    # NVIDIA GTX
    ("NVIDIA GeForce GTX 1060 6GB", "gpu", 7000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce GTX 1070 8GB", "gpu", 9000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce GTX 1070 Ti", "gpu", 10500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce GTX 1080 8GB", "gpu", 11500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce GTX 1080 Ti", "gpu", 14000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce GTX 1660 6GB", "gpu", 10500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce GTX 1660 Super", "gpu", 12500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce GTX 1660 Ti", "gpu", 13000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    # NVIDIA RTX 20 series
    ("NVIDIA GeForce RTX 2060", "gpu", 14000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 2060 Super", "gpu", 18500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 2070", "gpu", 19500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 2070 Super", "gpu", 22000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 2080", "gpu", 23000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 2080 Super", "gpu", 26000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 2080 Ti", "gpu", 28000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    # NVIDIA RTX 30 series
    ("NVIDIA GeForce RTX 3050", "gpu", 16500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 3060 12GB", "gpu", 24000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 3060 Ti", "gpu", 26500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 3070", "gpu", 29000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 3070 Ti", "gpu", 34000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 3080", "gpu", 38000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 3080 Ti", "gpu", 45000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    # NVIDIA RTX 40 series
    ("NVIDIA GeForce RTX 4060", "gpu", 28500, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 4060 Ti", "gpu", 35000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 4070", "gpu", 48000, "Медианный рыночный ориентир цен (Авито Б/У)"),
    ("NVIDIA GeForce RTX 4070 Super", "gpu", 55000, "Медианный рыночный ориентир цен (Авито Б/У)"),
]

def apply_fixes(db_path="catalog.db"):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # 1. Purge junk, broken, buyback and egpu listings from products
    junk_patterns = [
        r'\bартефакт\b', r'\bартефачит\b', r'\bпод ремонт\b', r'\bна запчаст\b', r'\bнерабоч\b', r'\bне рабоч\b',
        r'\bдефект\b', r'\bс проблемой\b', r'\bс нюансом\b', r'\bполоман\b', r'\bдонор\b',
        r'\bскупк\b', r'skupka', r'\bвыкуп\b', r'vykup', r'с моей доплатой', r'обмен на',
        r'\begpu\b', r'\bthunderbolt\b', r'\bcmp\s*40\b', r'\bcmp40\b', r'\bmi50\b'
    ]
    cur.execute("SELECT id, name FROM products WHERE category = 'gpu'")
    gpu_rows = cur.fetchall()
    deleted_junk = 0
    for pid, name in gpu_rows:
        nl = name.lower()
        if any(re.search(p, nl) for p in junk_patterns):
            cur.execute("DELETE FROM products WHERE id = ?", (pid,))
            cur.execute("DELETE FROM products_fts WHERE id = ?", (pid,))
            deleted_junk += 1
    print(f"Purged {deleted_junk} junk/broken/eGPU products.")

    # 2. Update/insert expert_components
    for comp_name, comp_type, price, comment in GPU_MEDIANS:
        # Check if already exists by chip/name
        chip = extract_chipset(comp_name)
        existing = cur.execute("SELECT id, componentname FROM expert_components WHERE type = 'gpu' AND componentname LIKE ?", (f"%{chip}%",)).fetchall()
        
        # Exact match or find best
        matched_id = None
        for eid, ename in existing:
            if extract_chipset(ename) == chip:
                matched_id = eid
                break
                
        if matched_id:
            cur.execute("""
                UPDATE expert_components 
                SET price = ?, comment = ?, analogue = '', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (price, comment, matched_id))
            print(f"Updated #{matched_id} {comp_name} -> {price} ₽")
        else:
            cur.execute("""
                INSERT INTO expert_components (type, componentname, price, comment, analogue, created_at, updated_at)
                VALUES (?, ?, ?, ?, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (comp_type, comp_name, price, comment))
            print(f"Inserted new expert component: {comp_name} -> {price} ₽")

    con.commit()
    
    # 3. Re-sync Avito products in database with new clean medians
    cur.execute("SELECT id, type, componentname, price, mark, comment FROM expert_components")
    expert_rows = [
        {"id": r[0], "type": r[1], "componentname": r[2], "price": r[3], "mark": r[4], "comment": r[5]}
        for r in cur.fetchall()
    ]
    
    cur.execute("SELECT id, name, category, price FROM products WHERE category = 'gpu' AND (shop LIKE '%Авито%' OR url LIKE '%avito%')")
    avito_gpus = cur.fetchall()
    
    updated_avito = 0
    for pid, name, cat, curr_p in avito_gpus:
        med_price = resolve_avito_median_price(name, cat, curr_p, expert_rows)
        if med_price and med_price != curr_p:
            cur.execute("UPDATE products SET price = ? WHERE id = ?", (med_price, pid))
            updated_avito += 1
            
    con.commit()
    print(f"Updated {updated_avito} / {len(avito_gpus)} Avito GPU products to true median prices.")
    con.close()

if __name__ == "__main__":
    apply_fixes()
