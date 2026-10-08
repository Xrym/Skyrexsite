"""
CLI Скрипт ручного или автоматического запуска сбора цен с ДНС и Ситилинк
Использование:
  python run_scraper.py --shop citilink --pages 1 --cat gpu cpu
  python run_scraper.py --shop dns --proxy http://user:pass@host:port
  python run_scraper.py --shop all
"""
import sys
import argparse

# Enable UTF-8 encoding in Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper.dns_worker import DnsScraper
from scraper.citilink_worker import CitilinkScraper
from scraper.onlinetrade_worker import OnlineTradeScraper
from db.database import get_stats

def main():
    parser = argparse.ArgumentParser(description="Skyrex PC Parts Scraper Worker")
    parser.add_argument("--shop", type=str, choices=["onlinetrade", "citilink", "dns", "all"], default="onlinetrade",
                        help="Выбор магазина: onlinetrade (по умолчанию), citilink, dns, all")
    parser.add_argument("--pages", type=int, default=1, help="Количество страниц на категорию (по умолчанию: 1)")
    parser.add_argument("--cat", nargs="+", help="Список категорий: gpu cpu motherboard ram ssd psu")
    parser.add_argument("--headless", action="store_true", help="Запуск в фоновом (скрытом) режиме без графического окна")

    args = parser.parse_args()

    print("=" * 60)
    print("[*] Запуск воркера сбора цен на комплектующие")
    print(f"[*] Магазин: {args.shop.upper()}")
    print(f"[*] Максимум страниц на категорию: {args.pages}")
    if args.cat:
        print(f"[*] Выбранные категории: {', '.join(args.cat)}")
    if args.proxy:
        print(f"[*] Прокси: {args.proxy.split('@')[-1]}")
    print("=" * 60)

    if args.shop in ["onlinetrade", "all"]:
        print("\n===> Запуск парсера ОнлайнТрейд...")
        onlinetrade = OnlineTradeScraper(headless=args.headless)
        onlinetrade.run_scrape_cycle(categories=args.cat, max_pages=args.pages)

    if args.shop in ["citilink", "all"]:
        print("\n===> Запуск парсера Ситилинк...")
        citilink = CitilinkScraper(proxy=args.proxy)
        citilink.run_scrape_cycle(categories=args.cat, max_pages=args.pages)

    if args.shop in ["dns", "all"]:
        print("\n===> Запуск парсера DNS-Shop...")
        dns = DnsScraper(proxy=args.proxy)
        dns.run_scrape_cycle(categories=args.cat, max_pages=args.pages)

    print("\n" + "=" * 60)
    print("[*] АКТУАЛЬНОЕ СОСТОЯНИЕ БАЗЫ ДАННЫХ CATALOG.DB:")
    db_stats = get_stats()
    print(f"Всего товаров в SQLite: {db_stats['total_products']}")
    print(f"По магазинам: {db_stats['by_shop']}")
    print(f"По категориям: {db_stats['by_category']}")
    print("=" * 60)

if __name__ == "__main__":
    main()
