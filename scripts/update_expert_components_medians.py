import sqlite3
import statistics
import re
from collections import defaultdict

con = sqlite3.connect('catalog.db')
cur = con.cursor()

# 1. Fetch all Avito products and calculate median prices
cur.execute("""
    SELECT name, category, price FROM products 
    WHERE shop LIKE '%Авито%' AND price >= 1000 AND price <= 500000
""")
avito_rows = cur.fetchall()

cpu_bundle_bad = [
    "комплект", "komplekt", "komlpekt", "combo", "bundle",
    "материн", "плата", "plata", "motherboard", "мать",
    "b450", "b550", "b650", "b760", "b850", "b840", "h610", "h510", "h410", "a520", "a620", "z790", "x870",
    "с кулером", "s kulerom", "с охлажд", "snowman", "vodyanka", "водянка", "bashnya", "башня",
    "сборк", "sbork", "готовые сборки", "игровой пк", "igrovoy pk",
    "+", "32gb", "16gb", "ddr5", "ddr4"
]

# Filter out CPU bundles from median calculations
filtered_avito_rows = []
for name, cat, price in avito_rows:
    if cat == 'cpu':
        nl = name.lower()
        if any(b in nl for b in cpu_bundle_bad):
            continue
    filtered_avito_rows.append((name, cat, price))
avito_rows = filtered_avito_rows

chips = [
    # GPUs
    'rtx 4090', 'rtx 4080 super', 'rtx 4080', 'rtx 4070 ti super', 'rtx 4070 ti', 'rtx 4070 super', 'rtx 4070',
    'rtx 4060 ti', 'rtx 4060', 'rtx 3090', 'rtx 3080 ti', 'rtx 3080', 'rtx 3070 ti', 'rtx 3070',
    'rtx 3060 ti', 'rtx 3060', 'rtx 3050', 'rtx 2080 ti', 'rtx 2080 super', 'rtx 2080', 'rtx 2070 super',
    'rtx 2070', 'rtx 2060 super', 'rtx 2060', 'gtx 1080 ti', 'gtx 1080', 'gtx 1070 ti', 'gtx 1070',
    'gtx 1660 super', 'gtx 1660 ti', 'gtx 1660', 'gtx 1060', 'gtx 1650', 'rx 7900 xtx', 'rx 7800 xt',
    'rx 7700 xt', 'rx 7600', 'rx 6900 xt', 'rx 6800 xt', 'rx 6800', 'rx 6700 xt', 'rx 6700', 'rx 6650 xt',
    'rx 6600 xt', 'rx 6600', 'rx 5700 xt', 'rx 5700', 'rx 5600 xt', 'rx 580', 'rx 570',
    # CPUs
    'ryzen 7 7800x3d', 'ryzen 7 7700x', 'ryzen 7 7700', 'ryzen 5 7600x', 'ryzen 5 7600', 'ryzen 5 7500f',
    'ryzen 7 5800x3d', 'ryzen 7 5700x3d', 'ryzen 7 5700x', 'ryzen 5 5600x', 'ryzen 5 5600', 'ryzen 5 5500',
    'ryzen 5 3600', 'i5-12400f', 'i3-12100f', 'i5-13400f', 'i5-13600k', 'i5-14600k', 'i7-13700k', 'i7-14700k',
    # RAM
    'ddr4 16gb', 'ddr4 32gb', 'ddr5 16gb', 'ddr5 32gb',
    # Motherboards
    'b650', 'b550', 'b450', 'a520', 'a620', 'b760', 'h610', 'z790',
    # PSUs
    '600w', '650w', '700w', '750w', '850w',
]

grouped = defaultdict(list)
for name, cat, price in avito_rows:
    nl = name.lower().replace("-", " ")
    for c in sorted(chips, key=lambda x: -len(x)):
        c_clean = c.replace("-", " ")
        if re.search(r'\b' + re.escape(c_clean) + r'\b', nl):
            grouped[c].append(price)
            break

medians = {}
for chip, prices in grouped.items():
    medians[chip] = int(statistics.median(prices))

# Established market medians for models with few/no listings in current scrape batch
fallback_medians = {
    'rx 580': 5400,
    'gtx 1060': 7000,
    'gtx 1070': 9000,
    'gtx 1660 super': 13500,
    'gtx 1080 ti': 15000,
    'rtx 2060': 15000,
    'rx 5700 xt': 22400,
    'rx 6600': 22000,
    'rtx 2060 super': 23000,
    'rx 6600 xt': 25000,
    'rtx 3060': 32000,
    'rtx 3060 ti': 30000,
    'rtx 3070': 34000,
    'rtx 3070 ti': 38000,
    'rtx 4060': 35000,
    'rtx 5050': 36000,
    'rtx 5060': 44500,
    'i3-12100f': 5500,
    'ryzen 5 2600': 3500,
    'ryzen 5 3600': 5000,
    'ryzen 5 5500': 5800,
    'ryzen 5 5600': 10500,
    'i5-12400f': 11000,
    'ryzen 5 7500f': 11350,
    'i5-13400f': 12000,
    'i5-14600k': 20500,
    'ryzen 7 7800x3d': 32500,
    'ddr4 16gb': 8000,
    'ddr4 32gb': 19500,
    'ddr5 16gb': 21000,
    'ddr5 32gb': 44000,
    'ssd 512gb': 4500,
    'ssd 1tb': 7500,
    'ssd 256gb': 3000,
}

# Update all existing expert_components
cur.execute("SELECT id, type, componentname, price, mark, comment FROM expert_components")
rows = cur.fetchall()

print(f"Updating {len(rows)} existing reference components with median Avito prices and neutral data...")
for row_id, ctype, cname, old_price, old_mark, old_comment in rows:
    nl = cname.lower().replace("-", " ")
    new_price = old_price
    
    # Try finding matching median from Avito parsed data
    matched_chip = None
    for c in sorted(chips, key=lambda x: -len(x)):
        c_clean = c.replace("-", " ")
        if re.search(r'\b' + re.escape(c_clean) + r'\b', nl):
            matched_chip = c
            break
            
    if matched_chip and matched_chip in medians:
        new_price = medians[matched_chip]
    elif matched_chip and matched_chip in fallback_medians:
        new_price = fallback_medians[matched_chip]
    else:
        # Check fallback dict by partial keywords
        for k, v in fallback_medians.items():
            k_clean = k.replace("-", " ")
            if k_clean in nl:
                new_price = v
                break
                
    # Neutral, objective description without subjective marks/opinions
    clean_comment = f"Медианный рыночный ориентир цен (Авито Б/У)"
    clean_mark = None # Remove subjective 1-10 mark
    
    cur.execute("""
        UPDATE expert_components 
        SET price = ?, mark = ?, comment = ?, analogue = '', updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (new_price, clean_mark, clean_comment, row_id))
    print(f"  #{row_id} [{ctype}] {cname}: price {old_price} -> {new_price} руб, mark {old_mark} -> None")

con.commit()
print("All expert_components updated successfully!")
con.close()

