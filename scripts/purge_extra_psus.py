import sqlite3

def purge_extra_psus():
    db_path = 'catalog.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    psu_junk_filter = """
        category = 'psu' AND NOT (
            (name LIKE '%Powercase%' AND (name LIKE '%PW500%' OR name LIKE '%PW600%' OR name LIKE '%PW700%' OR name LIKE '%PW 500%' OR name LIKE '%PW 600%' OR name LIKE '%PW 700%' OR name LIKE '%PW-500%' OR name LIKE '%PW-600%' OR name LIKE '%PW-700%'))
            OR ((name LIKE '%GAMERSTORM%' OR name LIKE '%Deepcool%' OR name LIKE '%DeepCool%') AND (name LIKE '%PF600%' OR name LIKE '%PF650%' OR name LIKE '%PF700%' OR name LIKE '%PF750%' OR name LIKE '%PF800%' OR name LIKE '%PF850%' OR name LIKE '%PF 600%' OR name LIKE '%PF 650%' OR name LIKE '%PF 700%' OR name LIKE '%PF 750%' OR name LIKE '%PF 800%' OR name LIKE '%PF 850%'))
            OR (name LIKE '%1STPLAYER%' AND name LIKE '%NGDP%' AND name NOT LIKE '%1200%')
        )
    """

    cur.execute(f"SELECT id, name, price FROM products WHERE {psu_junk_filter}")
    to_delete = cur.fetchall()
    print(f"Found {len(to_delete)} unapproved PSUs to delete.")

    cur.execute(f"DELETE FROM products_fts WHERE id IN (SELECT id FROM products WHERE {psu_junk_filter})")
    cur.execute(f"DELETE FROM products WHERE {psu_junk_filter}")
    conn.commit()

    cur.execute("SELECT id, shop, name, price FROM products WHERE category = 'psu' ORDER BY price ASC")
    remaining = cur.fetchall()
    print(f"\nRemaining approved PSUs ({len(remaining)} total):")
    for r in remaining:
        print(f"  [{r[1]}] #{r[0]}: {r[2]} — {r[3]} руб")

    conn.close()

if __name__ == '__main__':
    purge_extra_psus()
