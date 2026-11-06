import sqlite3
import statistics
import re
from collections import defaultdict

con = sqlite3.connect('catalog.db')
cur = con.cursor()

cur.execute("""
    SELECT name, category, price FROM products 
    WHERE shop LIKE '%Авито%' AND price >= 1000 AND price <= 500000
""")
avito_rows = cur.fetchall()
print(f"Total valid Avito products: {len(avito_rows)}")

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
    'ryzen 5 3600', 'i5-12400f', 'i5 12400f', 'i3-12100f', 'i3 12100f', 'i5-13400f', 'i5 13400f',
    'i5-13600k', 'i5 13600k', 'i5-14600k', 'i7-13700k', 'i7-14700k',
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

print("\nMedian Avito prices for detected chips:")
medians = {}
for chip, prices in sorted(grouped.items()):
    if len(prices) >= 1:
        med = int(statistics.median(prices))
        medians[chip] = med
        print(f"{chip.upper()}: median {med:,} руб (count: {len(prices)}, min: {min(prices):,}, max: {max(prices):,})")

con.close()

