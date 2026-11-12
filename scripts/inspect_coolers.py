import sqlite3

con = sqlite3.connect('catalog.db')
cur = con.cursor()

print('=== SOUND CARDS / JUNK IN PRODUCTS ===')
cur.execute("""
    SELECT id, shop, category, name, price, url 
    FROM products 
    WHERE url LIKE '%zvukovye_karty%' 
       OR name LIKE '%звуков%'
       OR name LIKE '%audio usb%'
       OR name LIKE '%звук%'
""")
rows = cur.fetchall()
print(f'Total sound cards / audio junk found: {len(rows)}')
for r in rows:
    print(f'#{r[0]} [{r[1]}] [{r[2]}] {r[3][:60]} - {r[4]} руб')

print('\n=== ALL PRODUCTS IN COOLER CATEGORY ===')
cur.execute("""
    SELECT id, shop, name, price, url 
    FROM products 
    WHERE category = 'cooler'
""")
coolers = cur.fetchall()
print(f'Total items in cooler: {len(coolers)}')
for r in coolers:
    print(f'#{r[0]} [{r[1]}] {r[2][:60]} - {r[3]} руб')

con.close()

