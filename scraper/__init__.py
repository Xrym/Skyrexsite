from .onlinetrade_worker import OnlineTradeScraper, ONLINETRADE_CATEGORIES
from .wildberries_worker import WildberriesScraper, WILDBERRIES_CATEGORIES
from .avito_worker import AvitoScraper, AVITO_CATEGORIES

__all__ = [
    "OnlineTradeScraper",
    "ONLINETRADE_CATEGORIES",
    "WildberriesScraper",
    "WILDBERRIES_CATEGORIES",
    "AvitoScraper",
    "AVITO_CATEGORIES"
]
