import sqlite3

con = sqlite3.connect('catalog.db')
cur = con.cursor()

print("=== ACTUAL COOLERS IN PRODUCTS ===")
cur.execute("""
    SELECT id, shop, category, name, price, url 
    FROM products 
    WHERE name LIKE '%кулер%' 
       OR name LIKE '%охлаждени%' 
       OR name LIKE '%se-2%'
       OR name LIKE '%cr-1000%'
       OR name LIKE '%ak400%'
       OR name LIKE '%ak620%'
       OR name LIKE '%ag400%'
""")
rows = cur.fetchall()
print(f"Total matching cooler keywords: {len(rows)}")
for r in rows:
    print(f"#{r[0]} [{r[1]}] [{r[2]}] {r[3][:50]} - {r[4]} руб")

print("\n=== BREAKDOWN OF CATEGORY 'COOLER' ===")
cur.execute("SELECT id, shop, name, price, url FROM products WHERE category = 'cooler'")
c_rows = cur.fetchall()
print(f"Total in category cooler: {len(c_rows)}")
for r in c_rows:
    print(f"#{r[0]} [{r[1]}] {r[2][:60]} - {r[3]} руб")

con.close()

