import sqlite3

conn = sqlite3.connect('catalog.db')
cursor = conn.cursor()

cursor.execute("UPDATE ai_rules SET title = 'Кулер для процессора' WHERE id = 15")
cursor.execute("UPDATE ai_rules SET title = 'Корпус для ПК' WHERE id = 16")
cursor.execute("UPDATE ai_rules SET title = 'Оперативная память: совместимость и объем' WHERE id = 13")
conn.commit()
conn.close()
print("Rule titles cleaned.")
