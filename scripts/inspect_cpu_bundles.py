import sqlite3

def check(db_path='catalog.db'):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("""
        SELECT id, shop, name, price, url 
        FROM products 
        WHERE category = 'cpu' 
          AND (
            name LIKE '%материн%' 
            OR name LIKE '%мать%' 
            OR name LIKE '%плата%' 
            OR name LIKE '%motherboard%' 
            OR name LIKE '%комплект%' 
            OR name LIKE '%+%'
            OR name LIKE '%combo%'
            OR name LIKE '%bundle%'
            OR name LIKE '%b450%'
            OR name LIKE '%b550%'
            OR name LIKE '%b650%'
            OR name LIKE '%b760%'
            OR name LIKE '%h610%'
            OR name LIKE '%h510%'
            OR name LIKE '%z790%'
            OR name LIKE '%x570%'
            OR name LIKE '%a520%'
            OR name LIKE '%komplekt%'
            OR name LIKE '%komlpekt%'
            OR name LIKE '%с кулером%'
            OR name LIKE '%s kulerom%'
            OR name LIKE '%с охлажд%'
            OR name LIKE '%кулер%'
          )
    """)
    rows = cur.fetchall()
    print(f"[{db_path}] Total bundle CPUs found: {len(rows)}")
    for r in rows:
        print(f"  #{r[0]} [{r[1]}] {r[2]} - {r[3]} руб")
    con.close()
    return rows

if __name__ == '__main__':
    check()

