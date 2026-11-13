import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlite3
from bot_tools.hardware_matcher import resolve_avito_median_price
from db.database import get_expert_components

def sync_avito_prices_in_db(db_path: str = "catalog.db"):
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    
    # Fetch expert components
    cur.execute("SELECT id, type, componentname, price, mark, comment FROM expert_components")
    expert_rows = [
        {"id": r[0], "type": r[1], "componentname": r[2], "price": r[3], "mark": r[4], "comment": r[5]}
        for r in cur.fetchall()
    ]
    
    # Fetch all Avito items
    cur.execute(
        "SELECT id, name, category, price, shop, url FROM products WHERE shop LIKE '%Авито%' OR url LIKE '%avito%'"
    )
    avito_items = cur.fetchall()
    
    updated_count = 0
    for r in avito_items:
        p_id, name, cat, current_price, shop, url = r
        med_price = resolve_avito_median_price(name, cat, current_price, expert_rows)
        if med_price and med_price != current_price:
            cur.execute("UPDATE products SET price = ? WHERE id = ?", (med_price, p_id))
            updated_count += 1
            
    con.commit()
    con.close()
    print(f"[{db_path}] Successfully updated {updated_count} / {len(avito_items)} Avito products to median prices.")

if __name__ == "__main__":
    db_file = sys.argv[1] if len(sys.argv) > 1 else "catalog.db"
    sync_avito_prices_in_db(db_file)
