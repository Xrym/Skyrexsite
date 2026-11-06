import sqlite3

con = sqlite3.connect("catalog.db")
cur = con.cursor()

print("=== TABLES ===")
for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(" ", r[0])

print("\n=== EXPERT_COMPONENTS SCHEMA ===")
for r in cur.execute("PRAGMA table_info(expert_components)"):
    print(" ", r)

print("\n=== EXPERT_COMPONENTS ROWS ===")
print("Total rows:", cur.execute("SELECT COUNT(*) FROM expert_components").fetchone()[0])
for r in cur.execute("SELECT id, type, componentname, price, minprice, mark, comment FROM expert_components"):
    print(f"ID={r[0]} | Type={r[1]} | Name={r[2]} | Price={r[3]} | MinPrice={r[4]} | Mark={r[5]} | Comment={r[6]}")

print("\n=== AI_RULES ===")
for r in cur.execute("SELECT id, rule_text FROM ai_rules"):
    print(f"Rule {r[0]}: {r[1]}")

con.close()
