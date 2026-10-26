# -*- coding: utf-8 -*-
"""
Skyrex Computers - Интерактивное меню управления парсером цен
Позволяет выбрать магазин, категории, глубину сбора и отправить базу на сервер.
"""

import sys
import os
import subprocess

# Настройка UTF-8 для Windows консоли
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def get_python_exe():
    bin_py = os.path.expandvars(r"%LocalAppData%\Python\bin\python.exe")
    if os.path.isfile(bin_py):
        return bin_py
    return sys.executable

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_header(subtitle=""):
    clear_screen()
    print("=" * 66)
    print("        ⚡ SKYREX COMPUTERS - УПРАВЛЕНИЕ СБОРОМ ЦЕН ⚡")
    if subtitle:
        print(f"        {subtitle}")
    print("=" * 66)
    print()

def ask_choice(prompt: str, valid_choices: list, default: str) -> str:
    while True:
        try:
            choice = input(f"{prompt} [Enter = {default}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nВыход.")
            sys.exit(0)
        if not choice:
            return default
        if choice in valid_choices:
            return choice
        print(f"[!] Неверный ввод '{choice}'. Допустимые варианты: {', '.join(valid_choices)}")

def main():
    while True:
        # 1. Выбор магазина
        print_header("ЭТАП 1: ВЫБОР МАГАЗИНА")
        print("  [1] Wildberries  --> Видеокарты, SSD, ОЗУ, Материнские платы")
        print("  [2] ОнлайнТрейд  --> Блоки питания, Кулеры и СЖО, Корпуса")
        print("  [3] Все магазины --> Полный сбор по всем категориям")
        print("  [0] Выход")
        print()
        shop_choice = ask_choice("Выберите магазин (1-3, 0)", ["1", "2", "3", "0"], "1")
        
        if shop_choice == "0":
            print("\nЗавершение работы.")
            sys.exit(0)

        shop_map = {
            "1": "wildberries",
            "2": "onlinetrade",
            "3": "all"
        }
        shop_val = shop_map[shop_choice]

        # 2. Выбор категорий
        cat_param = []
        cat_desc = ""

        if shop_val == "wildberries":
            print_header("ЭТАП 2: КОМПОНЕНТЫ WILDBERRIES")
            print("  [1] ВСЕ категории WB (GPU, SSD, RAM, Материнки)")
            print("  [2] Только Видеокарты (GPU)")
            print("  [3] Только SSD накопители (SSD)")
            print("  [4] Только Оперативная память (RAM)")
            print("  [5] Только Материнские платы (Motherboard)")
            print()
            cat_choice = ask_choice("Выберите категорию (1-5)", ["1", "2", "3", "4", "5"], "1")
            
            wb_cat_map = {
                "1": ([], "Все категории WB (GPU, SSD, RAM, Motherboard)"),
                "2": (["gpu"], "Видеокарты [GPU]"),
                "3": (["ssd"], "SSD накопители [SSD]"),
                "4": (["ram"], "Оперативная память [RAM]"),
                "5": (["motherboard"], "Материнские платы [Motherboard]")
            }
            cat_param, cat_desc = wb_cat_map[cat_choice]

        elif shop_val == "onlinetrade":
            print_header("ЭТАП 2: КОМПОНЕНТЫ ОНЛАЙНТРЕЙД")
            print("  [1] ВСЕ категории ОнлайнТрейд (БП, Кулеры, Корпуса)")
            print("  [2] Только Блоки питания (PSU)")
            print("  [3] Только Кулеры и СЖО (Cooler)")
            print("  [4] Только Корпуса (Case)")
            print()
            cat_choice = ask_choice("Выберите категорию (1-4)", ["1", "2", "3", "4"], "1")

            ot_cat_map = {
                "1": ([], "Все категории ОнлайнТрейд (PSU, Cooler, Case)"),
                "2": (["psu"], "Блоки питания [PSU]"),
                "3": (["cooler"], "Кулеры и СЖО [Cooler]"),
                "4": (["case"], "Корпуса [Case]")
            }
            cat_param, cat_desc = ot_cat_map[cat_choice]

        else: # all
            cat_param = []
            cat_desc = "Все разрешенные категории (WB: GPU, SSD, RAM, MB | OT: PSU, Cooler, Case)"

        # 3. Глубина сбора
        print_header("ЭТАП 3: ГЛУБИНА СБОРА (СТРАНИЦ НА КАТЕГОРИЮ)")
        print("  [1] 1 страница (~80-100 товаров на категорию, быстро)")
        print("  [2] 2 страницы (~160-200 товаров на категорию, рекомендуется)")
        print("  [3] 4 страницы (Глубокий сбор)")
        print("  [4] Ввести свое число страниц")
        print()
        pages_choice = ask_choice("Выберите глубину (1-4)", ["1", "2", "3", "4"], "2")
        
        if pages_choice == "1":
            pages_val = 1
        elif pages_choice == "2":
            pages_val = 2
        elif pages_choice == "3":
            pages_val = 4
        else:
            while True:
                custom_p = input("Введите количество страниц (например, 3): ").strip()
                if custom_p.isdigit() and int(custom_p) > 0:
                    pages_val = int(custom_p)
                    break
                print("[!] Введите положительное целое число.")

        # 4. Режим окна
        print_header("ЭТАП 4: РЕЖИМ БРАУЗЕРА")
        print("  [1] С видимым окном браузера (рекомендуется, наглядно)")
        print("  [2] В фоновом режиме (Headless, без открытия окна)")
        print()
        hl_choice = ask_choice("Выберите режим (1-2)", ["1", "2"], "1")
        is_headless = (hl_choice == "2")

        # 5. Сводка и подтверждение
        print_header("ПОДТВЕРЖДЕНИЕ ПАРАМЕТРОВ")
        print(f"  • Магазин:         {shop_val.upper()}")
        print(f"  • Комплектующие:   {cat_desc}")
        print(f"  • Страниц на тип:  {pages_val}")
        print(f"  • Окно браузера:   {'Фоновый режим (Headless)' if is_headless else 'Видимое окно'}")
        if shop_val in ["wildberries", "all"]:
            print("  • Фильтры качества: Рейтинг >= 4.0 ★, отзывов >= 3 шт.")
        print("-" * 66)
        
        # Формирование команды
        python_exe = get_python_exe()
        cmd = [python_exe, os.path.join(PROJECT_ROOT, "run_scraper.py"), "--shop", shop_val, "--pages", str(pages_val)]
        if cat_param:
            cmd.extend(["--cat"] + cat_param)
        if is_headless:
            cmd.append("--headless")

        print("Команда запуска:")
        print("  " + " ".join(cmd))
        print("-" * 66)
        
        confirm = ask_choice("Начать сбор прямо сейчас? (Y/N)", ["Y", "y", "N", "n", "Д", "д", "Н", "н"], "Y")
        if confirm.lower() in ["n", "н"]:
            continue

        # Запуск скрапера
        print_header("ВЫПОЛНЕНИЕ СБОРА ЦЕН...")
        print(f"Запуск воркера: {' '.join(cmd)}\n")
        
        ret = subprocess.run(cmd, cwd=PROJECT_ROOT)
        
        print("\n" + "=" * 66)
        if ret.returncode == 0:
            print("  ✅ СБОР УСПЕШНО ЗАВЕРШЕН! БАЗА CATALOG.DB ОБНОВЛЕНА.")
        else:
            print(f"  ⚠️ Парсер завершил работу с кодом возврата {ret.returncode}.")
        print("=" * 66)
        print()

        # 6. Предложение отправить на сервер
        print("  Хотите отправить обновленную базу catalog.db на сервер хостинга?")
        print("  (Скрипт безопасно добавит новые товары, не трогая данные клиентов)")
        print()
        deploy_ask = ask_choice("Отправить базу на сервер? (Y/N)", ["Y", "y", "N", "n", "Д", "д", "Н", "н"], "Y")
        
        if deploy_ask.lower() in ["y", "д"]:
            print("\n[🚀] Выгрузка базы на сервер через deploy.py --db-only...")
            deploy_cmd = [python_exe, os.path.join(PROJECT_ROOT, "deploy.py"), "--db-only"]
            subprocess.run(deploy_cmd, cwd=PROJECT_ROOT)
        else:
            print("\nБаза сохранена локально в catalog.db.")
            print("Для отправки позже выполните в консоли: python deploy.py --db-only")

        print("\n" + "-" * 66)
        again = ask_choice("Выполнить еще один сбор или выйти? (1 = Еще сбор, 0 = Выход)", ["1", "0"], "0")
        if again == "0":
            print("\nВсе готово. До свидания!")
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        sys.exit(0)
