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
from scraper.wildberries_worker import WildberriesScraper
from db.database import get_stats

def main():
    parser = argparse.ArgumentParser(description="Skyrex PC Parts Price Updater")
    parser.add_argument(
        "--shop",
        choices=["onlinetrade", "wildberries", "all"],
        default="wildberries",
        help="Магазин для обновления цен: onlinetrade, wildberries, all (по умолчанию: wildberries)",
    )
    parser.add_argument("--pages", type=int, default=1, help="Количество страниц на категорию (по умолчанию: 1)")
    parser.add_argument("--cat", nargs="+", help="Список категорий: gpu cpu motherboard ram ssd psu cooler")
    parser.add_argument("--proxy", type=str, default=None, help="HTTP/SOCKS5 прокси")
    parser.add_argument("--headless", action="store_true", help="Запуск браузера без графического окна")
    parser.add_argument("--min-rating", type=float, default=4.0, help="Минимальный рейтинг товара для WB (по умолчанию: 4.0)")
    parser.add_argument("--min-feedbacks", type=int, default=3, help="Минимальное количество отзывов для WB (по умолчанию: 3)")
    parser.add_argument("--export-excel", type=str, default=None, help="Экспорт собранных данных в Excel (.xlsx)")
    parser.add_argument("--export-json", type=str, default=None, help="Экспорт собранных данных в JSON (.json)")
    parser.add_argument("--export-csv", type=str, default=None, help="Экспорт собранных данных в CSV (.csv)")

    args = parser.parse_args()

    print("=" * 60)
    print(f"[*] Запуск воркера сбора цен: {args.shop}")
    print(f"[*] Максимум страниц на категорию: {args.pages}")
    if args.cat:
        print(f"[*] Выбранные категории: {', '.join(args.cat)}")
    if args.min_rating:
        print(f"[*] Фильтр рейтинга WB: от {args.min_rating} ★")
    if args.min_feedbacks:
        print(f"[*] Фильтр отзывов WB: от {args.min_feedbacks} шт.")
    if args.proxy:
        print(f"[*] Прокси: {args.proxy.split('@')[-1]}")
    if args.export_excel:
        print(f"[*] Экспорт в Excel: {args.export_excel}")
    if args.export_json:
        print(f"[*] Экспорт в JSON: {args.export_json}")
    if args.export_csv:
        print(f"[*] Экспорт в CSV: {args.export_csv}")
    print("=" * 60)

    export_path = args.export_excel or args.export_json or args.export_csv
    export_fmt = "xlsx" if args.export_excel else ("json" if args.export_json else ("csv" if args.export_csv else None))

    shops = ["wildberries", "onlinetrade"] if args.shop == "all" else [args.shop]
    for shop in shops:
        print(f"\n===> Обновление цен: {shop}...")
        if shop == "wildberries":
            scraper = WildberriesScraper(
                headless=args.headless,
                proxy=args.proxy,
                min_rating=args.min_rating,
                min_feedbacks=args.min_feedbacks
            )
            scraper.run_scrape_cycle(
                categories=args.cat,
                max_pages=args.pages,
                export_format=export_fmt,
                export_path=export_path
            )
        elif shop == "onlinetrade":
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
