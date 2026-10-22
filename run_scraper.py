"""CLI for manually running supported store price scrapers."""
import sys
import argparse

# Enable UTF-8 encoding in Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from scraper.onlinetrade_worker import OnlineTradeScraper
from db.database import get_stats

def main():
    parser = argparse.ArgumentParser(description="Skyrex PC Parts Price Updater")
    parser.add_argument(
        "--shop",
        choices=["onlinetrade", "all"],
        default="onlinetrade",
        help="Магазин для обновления цен (по умолчанию: onlinetrade)",
    )
    parser.add_argument("--pages", type=int, default=1, help="Количество страниц на категорию (по умолчанию: 1)")
    parser.add_argument("--cat", nargs="+", help="Список категорий: gpu cpu motherboard ram ssd psu cooler case")
    parser.add_argument("--proxy", type=str, default=None, help="HTTP/SOCKS5 прокси для ОнлайнТрейд")
    parser.add_argument("--headless", action="store_true", help="Запуск браузера ОнлайнТрейд без графического окна")

    args = parser.parse_args()

    print("=" * 60)
    print(f"[*] Запуск воркера сбора цен: {args.shop}")
    print(f"[*] Максимум страниц на категорию: {args.pages}")
    if args.cat:
        print(f"[*] Выбранные категории: {', '.join(args.cat)}")
    if args.proxy:
        print(f"[*] Прокси: {args.proxy.split('@')[-1]}")
    print("=" * 60)

    shops = ["onlinetrade"] if args.shop == "all" else [args.shop]
    for shop in shops:
        print(f"\n===> Обновление цен: {shop}...")
        scraper = OnlineTradeScraper(headless=args.headless)
        scraper.run_scrape_cycle(categories=args.cat, max_pages=args.pages)

    print("\n" + "=" * 60)
    print("[*] АКТУАЛЬНОЕ СОСТОЯНИЕ БАЗЫ ДАННЫХ CATALOG.DB:")
    db_stats = get_stats()
    print(f"Всего товаров в SQLite: {db_stats['total_products']}")
    print(f"По магазинам: {db_stats['by_shop']}")
    print(f"По категориям: {db_stats['by_category']}")
    print("=" * 60)

if __name__ == "__main__":
    main()
