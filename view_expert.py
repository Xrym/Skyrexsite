# -*- coding: utf-8 -*-
"""
Skyrex Computers - Просмотр базы экспертных комплектующих и оценок
Использование:
    python view_expert.py              - показать все комплектующие из локальной базы catalog.db
    python view_expert.py --remote     - показать комплектующие с живого сервера https://skyrex.pro
    python view_expert.py gpu          - показать только видеокарты
    python view_expert.py cpu          - показать только процессоры
"""

import sys
import os
import sqlite3
import urllib.request
import json

# Настройка UTF-8 для Windows консоли
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "catalog.db")

CATEGORY_ICONS = {
    "gpu": "🎮 Видеокарта",
    "cpu": "🧠 Процессор",
    "motherboard": "🖲 Плата",
    "ram": "⚡️ ОЗУ (RAM)",
    "ssd": "💾 Накопитель",
    "psu": "🔌 Блок питания",
    "cooler": "❄️ Кулер",
    "case": "📦 Корпус",
    "other": "⚙️ Другое",
}

def print_table(components: list, title: str):
    print("=" * 95)
    print(f"       ⭐️ SKYREX COMPUTERS — {title.upper()} (Всего: {len(components)})")
    print("=" * 95)
    
    if not components:
        print(" [!] В базе пока нет добавленных экспертных комплектующих.")
        print("=" * 95)
        return

    # Заголовок таблицы
    print(f"{'ID':<4} | {'Категория':<14} | {'Оценка':<7} | {'Цена (ориентир)':<16} | {'Название и вердикт эксперта'}")
    print("-" * 95)

    for c in components:
        cid = c.get("id", "-")
        ctype = CATEGORY_ICONS.get(c.get("type", "other"), c.get("type", "other"))
        mark = f"{c.get('mark', '-')}/10"
        price_val = c.get("price")
        price = f"{price_val:,} ₽".replace(",", " ") if price_val else "—"
        name = c.get("componentname") or c.get("name") or "—"
        comment = (c.get("comment") or "").strip()
        analogue = (c.get("analogue") or "").strip()

        print(f"{cid:<4} | {ctype:<14} | ⭐️ {mark:<5} | {price:<16} | {name}")
        if comment:
            print(f"{' ':>23}   💬 Мнение: \"{comment}\"")
        if analogue:
            print(f"{' ':>23}   🔄 Аналоги: {analogue}")
        print("-" * 95)

def main():
    args = [a.lower() for a in sys.argv[1:]]
    is_remote = "--remote" in args or "-r" in args
    filter_type = next((a for a in args if not a.startswith("-")), None)

    if is_remote:
        url = "https://skyrex.pro/api/expert-components"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SkyrexViewer/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
                comps = data.get("components", [])
                if filter_type:
                    comps = [c for c in comps if c.get("type", "").lower() == filter_type]
                print_table(comps, f"Серверная база Skyrex ({url})")
        except Exception as e:
            print(f"[❌] Не удалось загрузить данные с сервера: {e}")
    else:
        if not os.path.exists(DB_PATH):
            print(f"[❌] Файл базы данных не найден по пути: {DB_PATH}")
            return

        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        
        query = "SELECT * FROM expert_components"
        params = []
        if filter_type:
            query += " WHERE type = ?"
            params.append(filter_type)
        query += " ORDER BY id DESC"

        rows = [dict(r) for r in cur.execute(query, params).fetchall()]
        con.close()

        print_table(rows, f"Локальная база ({DB_PATH})")

if __name__ == "__main__":
    main()
