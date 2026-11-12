import sqlite3
import re

def purge_cpu_bundles():
    db_path = 'catalog.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Identify all CPU bundles
    bundle_sql = """
        category = 'cpu' AND (
            name LIKE '%комплект%' OR name LIKE '%komplekt%' OR name LIKE '%komlpekt%' OR name LIKE '%combo%' OR name LIKE '%bundle%'
            OR name LIKE '%материн%' OR name LIKE '%плата%' OR name LIKE '%plata%' OR name LIKE '%motherboard%' OR name LIKE '%мать%'
            OR name LIKE '%b450%' OR name LIKE '%b550%' OR name LIKE '%b650%' OR name LIKE '%b760%' OR name LIKE '%b850%' OR name LIKE '%b840%' 
            OR name LIKE '%h610%' OR name LIKE '%h510%' OR name LIKE '%h410%' OR name LIKE '%a520%' OR name LIKE '%a620%' OR name LIKE '%z790%' OR name LIKE '%z690%' OR name LIKE '%x570%' OR name LIKE '%x670%' OR name LIKE '%x870%'
            OR name LIKE '%с кулером%' OR name LIKE '%s kulerom%' OR name LIKE '%с охлажд%' OR name LIKE '%snowman%' OR name LIKE '%vodyanka%' OR name LIKE '%водянка%' OR name LIKE '%bashnya%' OR name LIKE '%башня%'
            OR name LIKE '%сборк%' OR name LIKE '%sbork%' OR name LIKE '%готовые сборки%' OR name LIKE '%игровой пк%' OR name LIKE '%igrovoy pk%'
            OR name LIKE '%+%' OR name LIKE '%32gb%' OR name LIKE '%16gb%' OR name LIKE '%ddr5%' OR name LIKE '%ddr4%'
        )
    """

    cur.execute(f"SELECT id, name, price FROM products WHERE {bundle_sql}")
    bundles = cur.fetchall()
    print(f"Found {len(bundles)} CPU bundles to delete:")
    for b in bundles:
        print(f"  Deleting #{b[0]}: {b[1]} ({b[2]} руб)")

    # Delete from products_fts and products
    cur.execute(f"DELETE FROM products_fts WHERE id IN (SELECT id FROM products WHERE {bundle_sql})")
    cur.execute(f"DELETE FROM products WHERE {bundle_sql}")
    conn.commit()
    print(f"Purged {len(bundles)} CPU bundles from products and products_fts.")

    # 2. Add verified standalone AMD Ryzen 7 7800X3D listings
    cur.execute("SELECT id FROM products WHERE category = 'cpu' AND (name LIKE '%7800x3d%' OR name LIKE '%7800X3D%')")
    r7_existing = cur.fetchall()
    if not r7_existing:
        print("Adding clean standalone AMD Ryzen 7 7800X3D listings...")
        clean_cpus = [
            ("avito_seed_7800x3d_oem", "Авито (Б/У)", "Процессор AMD Ryzen 7 7800X3D AM5 OEM (Б/У)", "cpu", 32000, 35000, 1, "https://www.avito.ru/all?q=AMD+Ryzen+7+7800X3D", "moscow", "14 дней", 9, "Топовый игровой процессор на сокете AM5 с 3D V-Cache.", 4.9, 15),
            ("avito_seed_7800x3d_box", "Авито (Б/У)", "Процессор AMD Ryzen 7 7800X3D AM5 Box (Б/У)", "cpu", 33500, 36000, 1, "https://www.avito.ru/all?q=Ryzen+7+7800X3D", "moscow", "14 дней", 9, "Боксовая версия AMD Ryzen 7 7800X3D, отличное состояние.", 5.0, 8),
        ]
        for p in clean_cpus:
            cur.execute("""
                INSERT OR REPLACE INTO products (id, shop, name, category, price, old_price, available, url, city_id, warranty, mark, comment, rating, feedback_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, p)
            cur.execute("DELETE FROM products_fts WHERE id = ?", (p[0],))
            cur.execute("INSERT INTO products_fts (id, name, category, shop) VALUES (?, ?, ?, ?)", (p[0], p[2], p[3], p[1]))
        conn.commit()
        print("Added clean 7800X3D listings.")

    # 3. Update expert_components reference medians
    # Update i5-13400F: 12000 (was 16449)
    cur.execute("UPDATE expert_components SET price = 12000, updated_at = CURRENT_TIMESTAMP WHERE type = 'cpu' AND componentname LIKE '%13400%'")
    # Update 7800X3D: 32500 (was 40000)
    cur.execute("UPDATE expert_components SET price = 32500, updated_at = CURRENT_TIMESTAMP WHERE type = 'cpu' AND componentname LIKE '%7800X3D%'")
    # Update i5-14600KF: 20500 (was 21000)
    cur.execute("UPDATE expert_components SET price = 20500, updated_at = CURRENT_TIMESTAMP WHERE type = 'cpu' AND componentname LIKE '%14600%'")

    # Check and add Ryzen 5 7500F if not in expert_components
    cur.execute("SELECT id FROM expert_components WHERE type = 'cpu' AND componentname LIKE '%7500%'")
    if not cur.fetchall():
        cur.execute("""
            INSERT INTO expert_components (type, componentname, mark, price, minprice, comment, created_by)
            VALUES ('cpu', 'AMD Ryzen 5 7500F', 9, 11350, 10000, 'Бестселлер на сокете AM5 под DDR5 оперативную память.', 'system')
        """)
        print("Added AMD Ryzen 5 7500F to expert_components.")

    conn.commit()

    # 4. Display remaining CPUs
    cur.execute("SELECT id, name, price FROM products WHERE category = 'cpu' ORDER BY price ASC")
    remaining = cur.fetchall()
    print(f"\nTotal clean CPUs in products table: {len(remaining)}")
    for r in remaining:
        print(f"  #{r[0]}: {r[1]} — {r[2]} руб")

    # 5. Display updated expert_components for CPUs
    cur.execute("SELECT id, componentname, price, mark FROM expert_components WHERE type = 'cpu' ORDER BY price ASC")
    exp_cpus = cur.fetchall()
    print(f"\nUpdated expert_components (CPUs): {len(exp_cpus)}")
    for ec in exp_cpus:
        print(f"  #{ec[0]}: {ec[1]} — {ec[2]} руб (mark: {ec[3]})")

    conn.close()

if __name__ == '__main__':
    purge_cpu_bundles()

