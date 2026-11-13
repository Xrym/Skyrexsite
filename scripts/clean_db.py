import sqlite3

conn = sqlite3.connect('catalog.db')
cursor = conn.cursor()

# 1. Delete Avito PSUs (user table specifies PSU is Online Trade, Wildberries only)
cursor.execute("DELETE FROM products WHERE category = 'psu' AND shop LIKE '%Авито%'")
deleted_psu = cursor.rowcount
print(f"Deleted {deleted_psu} Avito PSUs.")

# 2. Delete garbage titles (e.g. 'Ещё\n3 фото')
cursor.execute("DELETE FROM products WHERE name LIKE 'Ещё%фото%' OR name LIKE '%фото\n%' OR length(trim(name)) < 5")
deleted_garbage = cursor.rowcount
print(f"Deleted {deleted_garbage} garbage titles.")

# 3. Clean 'Подробнее о «' and trailing '»' from OnlineTrade products
cursor.execute("""
    UPDATE products 
    SET name = replace(replace(name, 'Подробнее о «', ''), '»', '')
    WHERE shop LIKE '%ОнлайнТрейд%' AND name LIKE '%Подробнее о «%'
""")
updated_names = cursor.rowcount
print(f"Cleaned {updated_names} OnlineTrade titles.")

conn.commit()

# Verify remaining counts
print("\n--- NEW PRODUCT COUNTS ---")
for r in cursor.execute("SELECT category, shop, count(*) FROM products GROUP BY category, shop"):
    print(f"{r[0]:<15} | {r[1]:<25} | count: {r[2]}")

conn.close()

