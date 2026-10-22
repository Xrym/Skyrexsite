"""Асинхронный клиент карточек товаров Wildberries."""

import asyncio
import json
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

_WB_DETAIL_URL = (
    "https://card.wb.ru/cards/v1/detail"
    "?appType=1&curr=rub&dest=-1257786&spp=30&nm={articles}"
)
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


async def get_wb_components(articles: list[int]) -> dict[int, dict[str, Any]]:
    """Получает сведения о товарах WB; цена возвращается в рублях."""
    if not articles:
        return {}

    article_ids = set(articles)
    url = _WB_DETAIL_URL.format(articles=";".join(map(str, articles)))
    timeout = aiohttp.ClientTimeout(total=5)

    try:
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=_HEADERS,
        ) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                payload = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as error:
        logger.warning("Не удалось получить товары Wildberries: %s", error)
        return {}

    data = payload.get("data") if isinstance(payload, dict) else None
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list):
        logger.warning("Wildberries вернул ответ без списка data.products")
        return {}

    result: dict[int, dict[str, Any]] = {}
    for product in products:
        if not isinstance(product, dict):
            continue

        product_id = product.get("id")
        sale_price = product.get("salePriceU")
        if (
            not isinstance(product_id, int)
            or isinstance(product_id, bool)
            or product_id not in article_ids
            or not isinstance(sale_price, (int, float))
            or isinstance(sale_price, bool)
        ):
            continue

        result[product_id] = {
            "id": product_id,
            "name": product.get("name"),
            "brand": product.get("brand"),
            "price": sale_price / 100,
        }

    return result
