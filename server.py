import os
import re
import json
import time
import socket
import logging
import secrets
import asyncio
import urllib.parse
from urllib.parse import urlparse
from collections import defaultdict
from typing import Optional, Dict, Any, List
import aiohttp
from aiohttp import web
import dotenv

# Chat rate limiter: max 20 requests per minute per IP
CHAT_RATE_LIMITS = defaultdict(list)
CHAT_MAX_REQUESTS_PER_MINUTE = 20

def check_rate_limit(ip: str) -> bool:
    """Enforces rate limiting per IP address to avoid API quota exhaustion."""
    now = time.time()
    valid_ts = [t for t in CHAT_RATE_LIMITS[ip] if now - t < 60]
    if len(valid_ts) >= CHAT_MAX_REQUESTS_PER_MINUTE:
        return False
    valid_ts.append(now)
    CHAT_RATE_LIMITS[ip] = valid_ts
    return True

from tg_admin_bot import TelegramAdminBot

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("skyrex_server")

# Load environment variables from .env
dotenv.load_dotenv()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 1. Parse bot_db.js to obtain the structured catalog
def load_bot_db():
    db_path = os.path.join(PROJECT_ROOT, 'bot_db.js')
    if not os.path.exists(db_path):
        logger.warning(f"bot_db.js not found at {db_path}, catalog empty")
        return {"components": [], "bestpc": []}

    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            content = f.read()

        start_idx = content.find('{')
        end_idx = content.rfind('};')
        if start_idx == -1 or end_idx == -1:
            logger.error("Could not find Javascript object bounds in bot_db.js")
            return {"components": [], "bestpc": []}

        json_like = content[start_idx:end_idx + 1]
        json_like = re.sub(r'(?m)^(\s*)(\w+)\s*:', r'\1"\2":', json_like)
        json_like = re.sub(r'(?m)^\s*//.*$', '', json_like)
        db = json.loads(json_like)
        logger.info(
            "Loaded database: %s components, %s PC builds.",
            len(db.get("components", [])),
            len(db.get("bestpc", [])),
        )
        return db
    except Exception as error:
        logger.error("Failed to parse bot_db.js: %s", error)
        return {"components": [], "bestpc": []}


BOT_DB = load_bot_db()

from bot_tools import search_price, format_price_results
from bot_tools.hardware_matcher import match_expert_assessment, enrich_and_rank_products
from db.database import seed_from_bot_db, get_stats, get_connection, get_expert_components
from db.auth_db import (
    init_auth_db, login_user, register_user,
    get_user_by_token, logout_token
)
from scraper.scheduler import BackgroundPriceScheduler

# Ensure SQLite databases are initialized
seed_from_bot_db()
init_auth_db()

# 2. Hardware specs detector & budget extractor
def extract_budget(text: str) -> Optional[int]:
    """Extracts target PC build budget from user prompt (e.g., '500 000 руб', '150к', 'бюджет 70000')."""
    if not text:
        return None
    t = text.lower().replace(',', '.')
    
    # 1. Patterns like '500к', '500 k', '500 тыс', '500тысяч'
    m_k = re.search(r'(\d+(?:\.\d+)?)\s*(?:к|k|тыс|тысяч)\b', t)
    if m_k:
        val = float(m_k.group(1)) * 1000
        if 15000 <= val <= 10000000:
            return int(val)
            
    # 2. Keywords followed by number: 'бюджет 500 000', 'на 500 000', 'за 500 000', 'до 500 000'
    m_kw = re.search(r'(?:бюджет(?:ом)?|на|за|до|около|сумму|сумма|стоимост[ьюи])\s*:?\s*(\d[\d\s]{2,}\d|\d{4,})\s*(?:руб|р)?', t)
    if m_kw:
        cleaned = re.sub(r'\s+', '', m_kw.group(1))
        if cleaned.isdigit():
            val = int(cleaned)
            if 15000 <= val <= 10000000:
                return val

    # 3. Standalone numbers followed by 'руб' / 'р'
    m_rub = re.search(r'(\d[\d\s]{2,}\d|\d{4,})\s*(?:руб|рублей|р\b)', t)
    if m_rub:
        cleaned = re.sub(r'\s+', '', m_rub.group(1))
        if cleaned.isdigit():
            val = int(cleaned)
            if 15000 <= val <= 10000000:
                return val

    return None

def detect_hardware_specs(product: dict) -> dict:
    """Detects CPU/Motherboard socket, RAM generation (DDR4/DDR5), and PSU wattage."""
    name = product.get("name", "")
    cat = product.get("category", "")
    specs = {
        "socket": None,
        "ram_type": None,
        "psu_watts": None
    }
    
    # Socket detection
    if "AM5" in name or "Socket AM5" in name or re.search(r'Ryzen\s*(?:5|7|9)\s*(?:7\d{3}|8\d{3}|9\d{3})', name, re.I) or re.search(r'\b(?:X870|B850|B650|A620|X670)\b', name):
        specs["socket"] = "AM5"
    elif "AM4" in name or "Socket AM4" in name or re.search(r'Ryzen\s*(?:3|5|7|9)\s*(?:1\d{3}|2\d{3}|3\d{3}|4\d{3}|5\d{3})', name, re.I) or re.search(r'\b(?:B550|A520|B450|X570|A320)\b', name):
        specs["socket"] = "AM4"
    elif "1851" in name or "LGA 1851" in name or "LGA1851" in name or re.search(r'\b(?:Z890|B860)\b', name) or "Ultra 9" in name or "Ultra 7" in name or "Ultra 5" in name:
        specs["socket"] = "LGA 1851"
    elif "1700" in name or "LGA 1700" in name or "LGA1700" in name or re.search(r'i[3579]\s*(?:12\d{3}|13\d{3}|14\d{3})', name, re.I) or re.search(r'\b(?:B760|Z790|H610|W680|Z690|B660)\b', name):
        specs["socket"] = "LGA 1700"
    elif "sTR5" in name or "Threadripper" in name:
        specs["socket"] = "sTR5"
    elif "1200" in name or "LGA 1200" in name:
        specs["socket"] = "LGA 1200"
    elif "1151" in name or "LGA 1151" in name:
        specs["socket"] = "LGA 1151"

    # RAM Type
    if "DDR5" in name:
        specs["ram_type"] = "DDR5"
    elif "DDR4" in name:
        specs["ram_type"] = "DDR4"
    elif "DDR3" in name:
        specs["ram_type"] = "DDR3"
    elif specs["socket"] in ("AM5", "LGA 1851"):
        specs["ram_type"] = "DDR5"
    elif specs["socket"] == "AM4":
        specs["ram_type"] = "DDR4"

    # PSU Watts
    if cat == "psu":
        m_w = re.search(r'(\d{3,4})\s*(?:Вт|W|ватт)\b', name, re.I)
        if m_w:
            specs["psu_watts"] = int(m_w.group(1))

    return specs

# 3. Dynamic context retrieval with budget awareness & hardware compatibility
def get_parsed_catalog_context(user_message: str) -> str:
    """Dynamically fetches real parsed products from SQLite catalog.db based on budget, query, and strict compatibility."""
    context_parts = []
    specific_results = []
    
    # 1. Search for specific items mentioned in user message (e.g. 'RTX 4070', 'Ryzen 7500F', 'Kingston')
    if user_message:
        raw_text = user_message.lower()
        search_terms = []

        # Find specific GPU / CPU models (e.g. "RTX 4070", "RX 7800", "GTX 1660", "Ryzen 5 7500F", "i5 13400")
        hw_patterns = [
            r'\b(?:rtx|gtx|rx|radeon|geforce)\s*\d{3,5}(?:\s*(?:ti|super|xt|xtx|gre))?\b',
            r'\b(?:ryzen\s*\d\s*\d{4}[a-z]*|ryzen\s*\d{4}[a-z]*)\b',
            r'\b(?:core\s*i[3579]\s*\d{4,5}[a-z]*|i[3579]\s*[- ]?\d{4,5}[a-z]*)\b',
            r'\b(?:b650|b550|b760|z790|z890|b850|a620|x670|x870)\b'
        ]
        for pat in hw_patterns:
            for match in re.finditer(pat, raw_text, re.IGNORECASE):
                term = match.group(0).strip()
                if term not in search_terms:
                    search_terms.append(term)

        # Bigrams of words (e.g. "kingston fury", "deepcool ak620", "be quiet")
        raw_words = [w for w in re.sub(r'[^\w\s]', ' ', user_message).split() if len(w) >= 2]
        for i in range(len(raw_words) - 1):
            pair = f"{raw_words[i]} {raw_words[i+1]}"
            if len(pair) >= 5 and pair not in search_terms and not (raw_words[i].isdigit() and raw_words[i+1].isdigit()):
                if any(k in pair.lower() for k in ['rtx', 'gtx', 'rx', 'ryzen', 'intel', 'amd', 'deepcool', 'kingston', 'asus', 'msi', 'gigabyte', 'palit', 'montech', 'cougar', 'be quiet', 'corsair', 'id-cooling', 'samsung', 'adata']):
                    search_terms.append(pair)

        # Fallback words
        stopwords = {
            'сборка', 'собери', 'купить', 'сколько', 'стоит', 'компьютер', 'привет', 'подскажи', 'рублей', 'бюджет',
            'игровой', 'игровая', 'игровые', 'игрового', 'игры', 'игра', 'гейминг', 'гейминга',
            'пк', 'комп', 'системник', 'сборки', 'сборку', 'собрать', 'подбери', 'посоветуй',
            'для', 'руб', 'рублей', 'тысяч', 'тыс', 'к', 'от', 'до', 'хороший', 'мощный', 'новый', 'нового'
        }
        for w in raw_words:
            w_lower = w.lower()
            if len(w) >= 3 and w_lower not in stopwords and not w.isdigit():
                if w not in search_terms:
                    search_terms.append(w)

        for term in search_terms[:6]:
            found = search_price(query=term, limit=4)
            for item in found:
                if not any(x['id'] == item['id'] for x in specific_results):
                    specific_results.append(item)
                    
    expert_components = get_expert_components(limit=300)
    specific_results = enrich_and_rank_products(specific_results, expert_components)

    general_build_keywords = ['пк', 'сборк', 'собери', 'компьютер', 'бюджет', 'детал', 'конфигурац', 'купить', 'ценами', 'ситилинк', 'цена', 'сколько']
    is_build_request = any(k in user_message.lower() for k in general_build_keywords)
    budget = extract_budget(user_message)
    
    # If this is a build request with budget, filter out specific results that exceed 60% of total budget
    if budget and is_build_request:
        specific_results = [p for p in specific_results if p.get('price', 0) <= int(budget * 0.60)]

    cat_items = []
    if is_build_request or budget or len(specific_results) < 5:
        with get_connection() as conn:
            # Determine target allocations if budget is specified
            max_gpu_price = int(budget * 0.55) if budget else 9999999
            max_cpu_price = int(budget * 0.28) if budget else 9999999
            max_mb_price = int(budget * 0.20) if budget else 9999999
            max_ram_price = int(budget * 0.16) if budget else 9999999
            max_ssd_price = int(budget * 0.14) if budget else 9999999
            max_psu_price = int(budget * 0.12) if budget else 9999999
            max_case_price = int(budget * 0.10) if budget else 9999999
            max_cooler_price = int(budget * 0.08) if budget else 9999999

            if budget:
                # Minimum ceilings so low budgets still find budget-tier parts in the catalog
                max_mb_price = max(max_mb_price, 8500)
                max_ram_price = max(max_ram_price, 12500)
                max_ssd_price = max(max_ssd_price, 6500)
                max_psu_price = max(max_psu_price, 6000)
                max_case_price = max(max_case_price, 5000)
                max_cooler_price = max(max_cooler_price, 3500)

            # A. Select Candidate GPUs fitting budget (enriched & ranked by expert opinion, then price)
            raw_gpus = [dict(r) for r in conn.execute(
                "SELECT * FROM products WHERE category = 'gpu' AND price <= ? ORDER BY price DESC LIMIT 20",
                (max_gpu_price,)
            ).fetchall()]
            if not raw_gpus:
                raw_gpus = [dict(r) for r in conn.execute("SELECT * FROM products WHERE category = 'gpu' ORDER BY price ASC LIMIT 20").fetchall()]
            cat_items.extend(enrich_and_rank_products(raw_gpus, expert_components, limit=5))

            # B. Select Candidate CPUs fitting budget (exclude workstation Threadripper > 150k unless requested)
            cpu_filter_threadripper = " AND name NOT LIKE '%Threadripper%' " if (not budget or budget < 1000000) else ""
            raw_cpus = [dict(r) for r in conn.execute(
                f"SELECT * FROM products WHERE category = 'cpu' AND price <= ? {cpu_filter_threadripper} ORDER BY price DESC LIMIT 20",
                (max_cpu_price,)
            ).fetchall()]
            if not raw_cpus:
                raw_cpus = [dict(r) for r in conn.execute(f"SELECT * FROM products WHERE category = 'cpu' {cpu_filter_threadripper} ORDER BY price ASC LIMIT 20").fetchall()]
            
            # If products table has no CPUs, provide curated reference CPUs for target budget
            if not raw_cpus:
                if budget and budget < 35000:
                    raw_cpus = [
                        {"id": "ref_cpu_r5_2600", "shop": "Вторичный рынок (Авито)", "category": "cpu", "name": "Процессор AMD Ryzen 5 2600 (Socket AM4, 6 ядер / 12 потоков)", "price": 3000, "url": "https://www.avito.ru/all?q=Ryzen+5+2600"},
                        {"id": "ref_cpu_r5_3600", "shop": "Вторичный рынок (Авито)", "category": "cpu", "name": "Процессор AMD Ryzen 5 3600 (Socket AM4, 6 ядер / 12 потоков)", "price": 4000, "url": "https://www.avito.ru/all?q=Ryzen+5+3600"},
                        {"id": "ref_cpu_i3_12100f", "shop": "Вторичный рынок (Авито)", "category": "cpu", "name": "Процессор Intel Core i3-12100F (Socket LGA 1700, 4 ядра / 8 потоков)", "price": 4500, "url": "https://www.avito.ru/all?q=Core+i3-12100F"},
                    ]
                elif budget and budget < 75000:
                    raw_cpus = [
                        {"id": "ref_cpu_r5_5600", "shop": "Вторичный рынок / Маркетплейс", "category": "cpu", "name": "Процессор AMD Ryzen 5 5600 (Socket AM4, 6 ядер / 12 потоков)", "price": 8500, "url": "https://www.avito.ru/all?q=Ryzen+5+5600"},
                        {"id": "ref_cpu_i3_12100f", "shop": "Вторичный рынок (Авито)", "category": "cpu", "name": "Процессор Intel Core i3-12100F (Socket LGA 1700, 4 ядра / 8 потоков)", "price": 5000, "url": "https://www.avito.ru/all?q=Core+i3-12100F"},
                        {"id": "ref_cpu_i5_12400f", "shop": "Вторичный рынок / Маркетплейс", "category": "cpu", "name": "Процессор Intel Core i5-12400F (Socket LGA 1700, 6 ядер / 12 потоков)", "price": 9500, "url": "https://www.avito.ru/all?q=Core+i5-12400F"},
                    ]
                elif budget and budget < 130000:
                    raw_cpus = [
                        {"id": "ref_cpu_r5_7500f", "shop": "Маркетплейс / Вторичка", "category": "cpu", "name": "Процессор AMD Ryzen 5 7500F (Socket AM5, 6 ядер / 12 потоков, DDR5)", "price": 13500, "url": "https://www.avito.ru/all?q=Ryzen+5+7500F"},
                        {"id": "ref_cpu_i5_13400f", "shop": "Маркетплейс / Вторичка", "category": "cpu", "name": "Процессор Intel Core i5-13400F (Socket LGA 1700, 10 ядер / 16 потоков)", "price": 16000, "url": "https://www.avito.ru/all?q=Core+i5-13400F"},
                    ]
                else:
                    raw_cpus = [
                        {"id": "ref_cpu_r7_7800x3d", "shop": "Маркетплейс", "category": "cpu", "name": "Процессор AMD Ryzen 7 7800X3D (Socket AM5, 8 ядер / 16 потоков, 3D V-Cache)", "price": 42000, "url": "https://www.avito.ru/all?q=Ryzen+7+7800X3D"},
                        {"id": "ref_cpu_i7_14700kf", "shop": "Маркетплейс", "category": "cpu", "name": "Процессор Intel Core i7-14700KF (Socket LGA 1700, 20 ядер / 28 потоков)", "price": 38000, "url": "https://www.avito.ru/all?q=Core+i7-14700KF"},
                    ]

            selected_cpus = enrich_and_rank_products(raw_cpus, expert_components, limit=6)
            cat_items.extend(selected_cpus)

            # C. Detect Sockets of selected candidate CPUs to guarantee 100% MOTHERBOARD COMPATIBILITY
            candidate_sockets = set()
            for c in selected_cpus:
                specs = detect_hardware_specs(c)
                if specs["socket"]:
                    candidate_sockets.add(specs["socket"])

            # D. Select Motherboards matching candidate sockets (partitioned per socket to guarantee compatibility)
            all_mbs = [dict(r) for r in conn.execute(
                "SELECT * FROM products WHERE category = 'motherboard' AND price <= ? ORDER BY price DESC LIMIT 40",
                (max_mb_price,)
            ).fetchall()]
            if not all_mbs:
                all_mbs = [dict(r) for r in conn.execute("SELECT * FROM products WHERE category = 'motherboard' ORDER BY price ASC LIMIT 40").fetchall()]

            compatible_mbs = []
            for mb_dict in all_mbs:
                specs = detect_hardware_specs(mb_dict)
                if not candidate_sockets or specs["socket"] in candidate_sockets:
                    mb_dict["detected_socket"] = specs["socket"]
                    mb_dict["detected_ram"] = specs["ram_type"]
                    compatible_mbs.append(mb_dict)

            selected_mbs = []
            for target_socket in candidate_sockets:
                socket_mbs = [m for m in compatible_mbs if m.get("detected_socket") == target_socket]
                # If budget < 80000, prioritize DDR4 motherboards for LGA 1700 / AM4
                if budget and budget < 80000 and target_socket in ("LGA 1700", "AM4"):
                    ddr4_mbs = [m for m in socket_mbs if m.get("detected_ram") == "DDR4"]
                    if ddr4_mbs:
                        selected_mbs.extend(enrich_and_rank_products(ddr4_mbs, expert_components, limit=3))
                    ddr5_mbs = [m for m in socket_mbs if m.get("detected_ram") == "DDR5"]
                    if ddr5_mbs and len(ddr4_mbs) < 3:
                        selected_mbs.extend(enrich_and_rank_products(ddr5_mbs, expert_components, limit=1))
                else:
                    selected_mbs.extend(enrich_and_rank_products(socket_mbs, expert_components, limit=3))

            cat_items.extend(selected_mbs if selected_mbs else enrich_and_rank_products(compatible_mbs, expert_components, limit=6))

            # E. Detect RAM Types required by selected compatible motherboards (e.g. DDR5 for AM5/LGA 1851)
            active_mbs = selected_mbs if selected_mbs else compatible_mbs
            required_ram_types = set(mb["detected_ram"] for mb in active_mbs if mb.get("detected_ram"))
            ram_filter_sodimm = " AND name NOT LIKE '%SODIMM%' AND name NOT LIKE '%SO-DIMM%' AND name NOT LIKE '%ноутбук%' "
            all_rams = [dict(r) for r in conn.execute(
                f"SELECT * FROM products WHERE category = 'ram' {ram_filter_sodimm} AND price <= ? ORDER BY price DESC LIMIT 25",
                (max_ram_price,)
            ).fetchall()]
            if not all_rams:
                all_rams = [dict(r) for r in conn.execute(f"SELECT * FROM products WHERE category = 'ram' {ram_filter_sodimm} ORDER BY price ASC LIMIT 25").fetchall()]

            def get_ram_capacity(name):
                m_cap = re.search(r'(\d+)\s*(?:гб|gb)\b', name, re.I)
                if m_cap:
                    return int(m_cap.group(1))
                return 16

            filtered_market_rams = []
            for r_dict in all_rams:
                specs = detect_hardware_specs(r_dict)
                cap = get_ram_capacity(r_dict.get("name", ""))
                r_dict["detected_capacity"] = cap
                # Exclude single 8GB sticks priced over 10 000 руб (overpriced marketplace anomalies)
                if cap <= 8 and r_dict.get("price", 0) > 10000:
                    continue
                if not required_ram_types or specs["ram_type"] in required_ram_types or not specs["ram_type"]:
                    r_dict["detected_ram"] = specs["ram_type"]
                    filtered_market_rams.append(r_dict)

            # Sort market RAMs: largest capacity first, then lowest price (maximum volume per ruble)
            filtered_market_rams.sort(key=lambda x: (-x.get("detected_capacity", 16), x.get("price", 0)))

            # In secondary / budget builds, provide verified secondary market reference RAM with direct Avito search links
            ref_rams = [
                {
                    "id": "ref_ram_16gb_ddr4_used",
                    "shop": "Вторичный рынок (Авито)",
                    "category": "ram",
                    "name": "Комплект 16 ГБ DDR4 (2x8 ГБ, 3200MHz)",
                    "price": 8000,
                    "url": "https://www.avito.ru/all?q=16Gb+DDR4+2x8"
                },
                {
                    "id": "ref_ram_32gb_ddr4_used",
                    "shop": "Вторичный рынок (Авито)",
                    "category": "ram",
                    "name": "Комплект 32 ГБ DDR4 (2x16 ГБ, 3200MHz)",
                    "price": 14000,
                    "url": "https://www.avito.ru/all?q=32Gb+DDR4+2x16"
                }
            ]
            if not budget or budget >= 70000:
                ref_rams.append({
                    "id": "ref_ram_32gb_ddr5_used",
                    "shop": "Вторичный рынок / Каталог",
                    "category": "ram",
                    "name": "Комплект 32 ГБ DDR5 (2x16 ГБ, 6000MHz)",
                    "price": 18000,
                    "url": "https://www.avito.ru/all?q=32Gb+DDR5+6000MHz"
                })

            valid_ref_rams = []
            for rr in ref_rams:
                specs = detect_hardware_specs(rr)
                rr["detected_ram"] = specs["ram_type"]
                rr["detected_capacity"] = get_ram_capacity(rr["name"])
                if not required_ram_types or specs["ram_type"] in required_ram_types:
                    valid_ref_rams.append(rr)

            # Guaranteed reference RAM kits first, followed by best-value retail RAM
            combined_rams = valid_ref_rams + filtered_market_rams

            # In ultra-low budget (< 35 000 руб), retail RAM >= 8000 руб is inappropriate
            if budget and budget < 35000:
                combined_rams = [r for r in combined_rams if r.get('price', 0) <= 6000 or 'avito' in r.get('url', '')]

            cat_items.extend(enrich_and_rank_products(combined_rams, expert_components, limit=6))

            # F. Select PSUs fitting budget (ranked by expert rating)
            raw_psus = [dict(r) for r in conn.execute(
                "SELECT * FROM products WHERE category = 'psu' AND price <= ? ORDER BY price DESC LIMIT 20",
                (max_psu_price,)
            ).fetchall()]
            if not raw_psus:
                raw_psus = [dict(r) for r in conn.execute("SELECT * FROM products WHERE category = 'psu' ORDER BY price ASC LIMIT 20").fetchall()]
            cat_items.extend(enrich_and_rank_products(raw_psus, expert_components, limit=5))

            # G. Select SSDs fitting budget (diverse prices, prioritizing highest volume for lowest price)
            raw_ssds = [dict(r) for r in conn.execute(
                "SELECT * FROM products WHERE category = 'ssd' AND price <= ? ORDER BY price ASC LIMIT 35",
                (max_ssd_price,)
            ).fetchall()]
            if not raw_ssds:
                raw_ssds = [dict(r) for r in conn.execute("SELECT * FROM products WHERE category = 'ssd' ORDER BY price ASC LIMIT 35").fetchall()]

            def get_ssd_capacity(name):
                m_tb = re.search(r'(\d+)\s*(?:тб|tb)\b', name, re.I)
                if m_tb:
                    return int(m_tb.group(1)) * 1024
                m_gb = re.search(r'(\d{3,4})\s*(?:гб|gb)\b', name, re.I)
                if m_gb:
                    return int(m_gb.group(1))
                return 512

            for s in raw_ssds:
                s["detected_capacity"] = get_ssd_capacity(s.get("name", ""))

            # Sort candidate SSDs: highest capacity first, then lowest price (maximum volume for lowest price)
            ranked_ssds = sorted(raw_ssds, key=lambda x: (-x["detected_capacity"], x.get("price", 0)))

            diverse_ssds = []
            seen_ids = set()
            # 1. Best value by volume (largest capacity with lowest price)
            for s in ranked_ssds:
                if s["id"] not in seen_ids:
                    diverse_ssds.append(s)
                    seen_ids.add(s["id"])
                    if len(diverse_ssds) >= 3:
                        break

            # 2. Add variety of price points (budget to higher) so bot sees different price tiers
            for s in sorted(raw_ssds, key=lambda x: x.get("price", 0)):
                if s["id"] not in seen_ids:
                    diverse_ssds.append(s)
                    seen_ids.add(s["id"])
                    if len(diverse_ssds) >= 6:
                        break

            cat_items.extend(enrich_and_rank_products(diverse_ssds, expert_components, limit=6))

            # H. Select Coolers fitting budget (ranked by expert rating, ignore misclassified sound cards)
            raw_coolers = [dict(r) for r in conn.execute(
                "SELECT * FROM products WHERE category = 'cooler' AND name NOT LIKE '%звуков%' AND url NOT LIKE '%zvukovye_karty%' AND price <= ? ORDER BY price DESC LIMIT 20",
                (max_cooler_price,)
            ).fetchall()]
            if not raw_coolers:
                raw_coolers = [dict(r) for r in conn.execute("SELECT * FROM products WHERE category = 'cooler' AND name NOT LIKE '%звуков%' AND url NOT LIKE '%zvukovye_karty%' ORDER BY price ASC LIMIT 20").fetchall()]
            cat_items.extend(enrich_and_rank_products(raw_coolers, expert_components, limit=4))

            # I. Select Cases fitting budget (ranked by expert rating)
            raw_cases = [dict(r) for r in conn.execute(
                "SELECT * FROM products WHERE category = 'case' AND price <= ? ORDER BY price DESC LIMIT 20",
                (max_case_price,)
            ).fetchall()]
            if not raw_cases:
                raw_cases = [dict(r) for r in conn.execute("SELECT * FROM products WHERE category = 'case' ORDER BY price ASC LIMIT 20").fetchall()]
            cat_items.extend(enrich_and_rank_products(raw_cases, expert_components, limit=4))

    all_products = specific_results + [p for p in cat_items if not any(x['id'] == p['id'] for x in specific_results)]
    
    if all_products:
        budget_header = f" ПОД БЮДЖЕТ {budget:,} РУБ" if budget else ""
        context_parts.append(f"=== АКТУАЛЬНЫЕ ЦЕНЫ И НАЛИЧИЕ ИЗ ОНЛАЙНТРЕЙД (РЕАЛЬНЫЙ КАТАЛОГ{budget_header}) ===")
        if budget and budget < 35000:
            context_parts.append(
                f"⚠️ ПРАВИЛО УЛЬТРАНИЗКОГО БЮДЖЕТА ({budget:,} РУБ):\n"
                f"1. В бюджете до 35 000 руб. собрать ПК из новых магазинных комплектующих невозможно (одна плата и память съедят бюджет).\n"
                f"2. ПРАВИЛО ЧЕСТНОГО БЮДЖЕТА: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО говорить во вступлении 'Вот сборка под ваш бюджет {budget:,} руб.', а затем насчитывать сумму в 40 000 руб.!\n"
                f"   - Либо собери ПК ПОЛНОСТЬЮ на проверенном Б/У рынке (Авито) со ссылками на поиск Авито, чтобы итоговая сумма была ровно <= {budget:,} руб. (например: Ryzen 5 2600 + A320 + RX 580 8GB + 16GB DDR4 + БП + SSD = ровно до 20 000 руб.)!\n"
                f"   - Либо СРАЗУ в первой же строчке честно скажи клиенту: 'В бюджете {budget:,} руб. современную платформу i3/Ryzen собрать невозможно, минимальный порог для неё — около 35 000 – 40 000 руб. Вот оптимальная конфигурация на 40 000 руб...'."
            )
        for p in all_products[:45]:
            specs = detect_hardware_specs(p)
            spec_tags = []
            if specs["socket"]:
                socket_platform = ""
                if specs["socket"] in ("AM4", "AM5"):
                    socket_platform = " (для AMD Ryzen)"
                elif specs["socket"] in ("LGA 1700", "LGA 1851", "LGA 1200"):
                    socket_platform = " (для Intel Core)"
                spec_tags.append(f"Сокет: {specs['socket']}{socket_platform}")
            if specs["ram_type"]:
                spec_tags.append(f"Память: {specs['ram_type']}")
            if specs["psu_watts"]:
                spec_tags.append(f"Мощность: {specs['psu_watts']}W")
            tag_str = f" [{ ' | '.join(spec_tags) }]" if spec_tags else ""

            rating_str = ""
            if p.get("expert_mark") is not None:
                m_val = p["expert_mark"]
                c_txt = (p.get("expert_comment") or "").strip()
                e_name = p.get("expert_name") or ""
                m_type = p.get("expert_match") or ""
                if m_val >= 8:
                    badge = f"⭐️ Топ-оценка эксперта: {m_val}/10"
                elif m_val >= 6:
                    badge = f"✅ Одобрено экспертом: {m_val}/10"
                else:
                    badge = f"⛔️ НИЗКАЯ ОЦЕНКА ЭКСПЕРТА: {m_val}/10 (НЕ РЕКОМЕНДУЕТСЯ)"

                extra = []
                if c_txt:
                    extra.append(f"Вердикт: \"{c_txt}\"")
                if e_name and m_type == "family":
                    extra.append(f"правило для всей серии {e_name}")
                elif e_name and m_type == "edition":
                    extra.append(f"точное совпадение издания {e_name}")

                sub_info = f" | {' | '.join(extra)}" if extra else ""
                rating_str = f" [{badge}{sub_info}]"

            price_str = f"{p['price']:,} руб".replace(",", " ")
            old_str = f" (старая цена: {p['old_price']:,} руб)".replace(",", " ") if p.get('old_price') else ""
            context_parts.append(f"- [{p.get('shop', 'ОнлайнТрейд')}] [{p.get('category', '').upper()}] {p['name']}. Цена: {price_str}{old_str}{tag_str}{rating_str}. Ссылка: {p['url']}")

    return "\n".join(context_parts)

def clean_avito_links(text: str) -> str:
    """Гарантирует, что все ссылки на Авито ведут на страницу поиска по точному запросу,
    а не на выдуманные несуществующие прямые объявления.
    """
    if not text:
        return text

    # 1. Преобразование Markdown-ссылок [текст](url) в чистый HTML
    def md_link_replacer(match):
        title = match.group(1)
        url = match.group(2)
        return f"<a href='{url}' target='_blank'>{title}</a>"

    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', md_link_replacer, text)

    # 2. Коррекция HTML-ссылок на Авито
    def html_avito_replacer(match):
        full_tag = match.group(0)
        href = match.group(1)
        inner_text = match.group(2)

        if "avito.ru" in href:
            if "?q=" in href or "&q=" in href:
                try:
                    parsed = urllib.parse.urlparse(href)
                    params = urllib.parse.parse_qs(parsed.query)
                    raw_q = params.get('q', [''])[0]
                    clean_text = urllib.parse.unquote_plus(raw_q)
                    # If clean_text still contains broken '%' or corrupted tokens, fallback to inner_text
                    if '%' in clean_text or len(clean_text) < 2 or 'па0' in clean_text or 'такогонить' in clean_text:
                        clean_text = re.sub(r'<[^>]+>', '', inner_text).strip()
                    clean_text = re.sub(r'<[^>]+>', '', clean_text).strip()
                    clean_text = re.sub(r'(?i)\(б/у\)|б/у', '', clean_text).strip()
                    if clean_text:
                        reencoded_url = f"https://www.avito.ru/all?q={urllib.parse.quote_plus(clean_text)}"
                        return f"<a href='{reencoded_url}' target='_blank'>{inner_text}</a>"
                except Exception:
                    pass
                if 'target=' not in full_tag:
                    return f"<a href='{href}' target='_blank'>{inner_text}</a>"
                return full_tag

            clean_query = re.sub(r'<[^>]+>', '', inner_text).strip()
            clean_query = re.sub(r'(?i)\b(на\s+авито|авито|avito|купить|поиск|ссылка|объявление)\b', '', clean_query).strip()

            if not clean_query or len(clean_query) < 2:
                path = href.split("?")[0].rstrip("/").split("/")[-1]
                path = re.sub(r'_\d+$', '', path).replace('_', ' ').replace('-', ' ')
                clean_query = path.strip() or "компьютерные комплектующие"

            search_url = f"https://www.avito.ru/all?q={urllib.parse.quote_plus(clean_query)}"
            return f"<a href='{search_url}' target='_blank'>{inner_text}</a>"

        return full_tag

    html_a_pattern = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    text = html_a_pattern.sub(html_avito_replacer, text)

    # 3. Преобразование «сырых» ссылок на Авито в тексте
    def raw_avito_replacer(match):
        raw_url = match.group(0)
        start = match.start()
        prefix = text[max(0, start - 10):start]
        if 'href=' in prefix or 'src=' in prefix:
            return raw_url
        if "?q=" in raw_url:
            return f"<a href='{raw_url}' target='_blank'>Поиск на Авито</a>"
        path = raw_url.split("?")[0].rstrip("/").split("/")[-1]
        path = re.sub(r'_\d+$', '', path).replace('_', ' ').replace('-', ' ').strip()
        query = path or 'компьютерные комплектующие'
        search_url = f"https://www.avito.ru/all?q={urllib.parse.quote_plus(query)}"
        return f"<a href='{search_url}' target='_blank'>{query} на Авито</a>"

    text = re.sub(r'https?://(?:www\.)?avito\.ru/[^\s<>\'"]+', raw_avito_replacer, text)

    return text

# 4. Format database into highly descriptive instructions for LLM
def build_system_instruction(dynamic_context=""):
    from db.database import (
        get_ai_rules,
        get_expert_components,
        get_prompt_template,
    )

    try:
        db_components = get_expert_components(limit=150)
        components = db_components if db_components else BOT_DB.get("components", [])
    except Exception as error:
        logger.error("Error loading expert components: %s", error)
        components = BOT_DB.get("components", [])

    ai_rules = get_ai_rules(active_only=True)
    base_prompt = get_prompt_template("assistant_system")

    rules_text = ""
    if ai_rules:
        rules_text = (
            "=== СВОД ПРАВИЛ И ТЕХНИЧЕСКИХ СТАНДАРТОВ СБОРКИ SKYREX ===\n"
            "Неукоснительно следуй всем правилам ниже при консультации и подборе комплектующих:\n\n"
        )
        for r in ai_rules:
            rule_id = r.get("id", "")
            title = r.get("title") or "Инструкция"
            rule_text = r.get("rule_text", "").strip()
            rules_text += f"Правило #{rule_id} [{title}]:\n{rule_text}\n\n"

    catalog_text = "=== БАЗА МНЕНИЙ, ОЦЕНОК И РЕКОМЕНДАЦИЙ ЭКСПЕРТА SKYREX ===\n\n"
    for component in components:
        comp_name = component.get('componentname', 'Без названия')
        avito_query = urllib.parse.quote_plus(comp_name)
        avito_url = f"https://www.avito.ru/all?q={avito_query}"
        catalog_text += (
            f"- {comp_name} "
            f"({component.get('type', 'other').upper()}). "
        )
        if component.get('price'):
            catalog_text += f"Ориентир цены: {component['price']} руб. "
        if component.get("minprice"):
            catalog_text += f"(Минимальная цена: {component['minprice']} руб). "
        catalog_text += f"Экспертная оценка: {component.get('mark', 'N/A')}/10. "
        catalog_text += f"Ссылка на поиск Авито: {avito_url}. "
        comment = component.get("comment", "").replace("\n", " ")
        if comment:
            catalog_text += f"Вердикт/мнение эксперта: {comment} "
        analogue = component.get("analogue", "").replace("\n", " ")
        if analogue:
            catalog_text += f"Рекомендуемые аналоги: {analogue}"
        catalog_text += "\n"

    catalog_text += "\nГОТОВЫЕ ОПТИМИЗИРОВАННЫЕ СБОРКИ ПК (Б/У):\n"
    for pc in BOT_DB.get("bestpc", []):
        catalog_text += (
            f"- Сборка \"{pc.get('pcname', 'Без названия')}\". "
            f"Стоимость: {pc.get('pcprice', 'N/A')} руб. "
        )
        parts = []
        for component in pc.get("components", []):
            part = f"{component.get('name', '')} ({component.get('price', '')} руб)"
            if component.get("comment"):
                part += f" - {component['comment']}"
            parts.append(part)
        catalog_text += "Состав сборки:\n  " + "\n  ".join(parts) + "\n"
        comment = pc.get("pccomment", "").replace("\n", " ")
        if comment:
            catalog_text += f"  Вердикт эксперта: {comment}\n"
        catalog_text += "\n"

    prompt_sections = [base_prompt.strip()]
    if rules_text:
        prompt_sections.append(rules_text.strip())
    if catalog_text:
        prompt_sections.append(catalog_text.strip())
    if dynamic_context:
        prompt_sections.append(dynamic_context.strip())

    return "\n\n".join(prompt_sections)


def strip_html_for_history(text: str) -> str:
    """Removes HTML formatting tags from historical messages so LLM receives clean tokens."""
    if not text:
        return ""
    t = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    t = re.sub(r'<a\s+[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>', r'\2 (\1)', t, flags=re.I | re.S)
    t = re.sub(r'<[^>]+>', '', t)
    return t.strip()


def get_active_proxy(provider: str) -> Optional[str]:
    """Detects and returns active proxy configuration or None if unreachable/disabled."""
    llm_proxy = os.getenv("LLM_PROXY", "").strip() or None
    if llm_proxy and llm_proxy.lower() in ("none", "direct", "false", "off", "no"):
        llm_proxy = None

    if llm_proxy:
        try:
            p = urlparse(llm_proxy)
            p_host = p.hostname or "127.0.0.1"
            p_port = p.port or (443 if p.scheme == "https" else 80)
            with socket.create_connection((p_host, p_port), timeout=0.3):
                pass
        except Exception:
            logger.warning(f"Configured LLM proxy {llm_proxy} is unreachable. Falling back to direct connection.")
            llm_proxy = None

    if not llm_proxy and provider != "ollama":
        env_proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        if env_proxy:
            try:
                p = urlparse(env_proxy)
                p_host = p.hostname or "127.0.0.1"
                p_port = p.port or (443 if p.scheme == "https" else 80)
                with socket.create_connection((p_host, p_port), timeout=0.3):
                    llm_proxy = env_proxy
            except Exception:
                pass

        if not llm_proxy:
            for test_port in (2080, 10809, 7890, 10808):
                try:
                    with socket.create_connection(("127.0.0.1", test_port), timeout=0.2):
                        llm_proxy = f"http://127.0.0.1:{test_port}"
                        break
                except Exception:
                    pass
    return llm_proxy


# 3. Call LLM provider with retry & timeout protection
async def call_llm(message: str, history: list) -> str:
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    
    # Validation
    if not api_key and provider != "ollama":
        return (
            "⚠️ <b>Сервер запущен, но не настроен API-ключ.</b><br><br>"
            "Пожалуйста, откройте файл <code>.env</code> в корне папки <code>skyrex-main</code> "
            "и укажите ваш действующий API-ключ в переменной <code>LLM_API_KEY</code>.<br>"
            "Если вы хотите использовать бесплатный вариант, зарегистрируйтесь на <a href='https://openrouter.ai' target='_blank'>OpenRouter</a> "
            "или <a href='https://aistudio.google.com' target='_blank'>Google AI Studio (Gemini)</a>."
        )

    # Setup Defaults
    if provider == "gemini":
        if not model:
            model = "gemini-3.5-flash-lite"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    else:
        # OpenAI-compatible setup
        if provider == "openrouter":
            base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
            if not model:
                model = "meta-llama/llama-3.3-70b-instruct:free"
        elif provider == "groq":
            base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
            if not model:
                model = "llama-3.3-70b-versatile"
        elif provider == "ollama":
            base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
            if not model:
                model = "qwen2.5:7b"
        else:
            base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            if not model:
                model = "gpt-4o-mini"
                
        url = f"{base_url.rstrip('/')}/chat/completions"

    dynamic_context = get_parsed_catalog_context(message)
    system_instruction = build_system_instruction(dynamic_context)
    llm_proxy = get_active_proxy(provider)

    async with aiohttp.ClientSession(trust_env=True) as session:
        try:
            if provider == "gemini":
                contents = []
                for msg in history:
                    role = "user" if msg.get("sender") == "user" else "model"
                    contents.append({
                        "role": role,
                        "parts": [{"text": strip_html_for_history(msg.get("text", ""))}]
                    })
                contents.append({
                    "role": "user",
                    "parts": [{"text": message}]
                })
                
                payload = {
                    "systemInstruction": {
                        "parts": [{"text": system_instruction}]
                    },
                    "contents": contents,
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 8192
                    }
                }
                
                logger.info(f"Sending request to Gemini API (Model: {model}, Proxy: {llm_proxy or 'direct'})...")
                async with session.post(url, json=payload, proxy=llm_proxy, timeout=75) as resp:
                    if resp.status in (429, 503, 500):
                        err_text = await resp.text()
                        fallback_model = "gemini-3.5-flash-lite" if model != "gemini-3.5-flash-lite" else "gemini-flash-lite-latest"
                        logger.warning(f"Gemini API returned status {resp.status} with model {model}. Retrying with {fallback_model}...")
                        fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/{fallback_model}:generateContent?key={api_key}"
                        await asyncio.sleep(1.0)
                        try:
                            async with session.post(fallback_url, json=payload, proxy=llm_proxy, timeout=75) as fb_resp:
                                if fb_resp.status == 200:
                                    fb_res = await fb_resp.json()
                                    raw_text = fb_res["candidates"][0]["content"]["parts"][0]["text"]
                                    return clean_avito_links(raw_text)
                        except Exception as fb_err:
                            logger.error(f"Gemini fallback error: {fb_err}")
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"Gemini API returned status {resp.status}: {err_text}")
                        return f"⚠️ Ошибка Gemini API ({resp.status}). Пожалуйста, проверьте API-ключ в настройках."
                    
                    result = await resp.json()
                    try:
                        raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
                        return clean_avito_links(raw_text)
                    except (KeyError, IndexError) as e:
                        logger.error(f"Failed to parse Gemini response: {e}, structure: {result}")
                        return "⚠️ Не удалось распознать ответ от нейросети. Попробуйте еще раз."
            else:
                messages = [{"role": "system", "content": system_instruction}]
                for msg in history:
                    role = "user" if msg.get("sender") == "user" else "assistant"
                    messages.append({"role": role, "content": strip_html_for_history(msg.get("text", ""))})
                messages.append({"role": "user", "content": message})
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2048
                }
                
                headers = {}
                if provider != "ollama":
                    headers["Authorization"] = f"Bearer {api_key}"
                
                if provider == "openrouter":
                    headers["HTTP-Referer"] = "https://skyrex.ai"
                    headers["X-Title"] = "Skyrex Computers AI"
                
                logger.info(f"Sending request to OpenAI-compatible {provider} API (Model: {model}, Proxy: {llm_proxy or 'direct'})...")
                async with session.post(url, json=payload, headers=headers, proxy=llm_proxy, timeout=75) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"{provider.upper()} API returned status {resp.status}: {err_text}")
                        return f"⚠️ Ошибка {provider.upper()} API ({resp.status}). Убедитесь, что лимиты и ключ в порядке."
                    
                    result = await resp.json()
                    try:
                        raw_text = result["choices"][0]["message"]["content"]
                        return clean_avito_links(raw_text)
                    except (KeyError, IndexError) as e:
                        logger.error(f"Failed to parse OpenAI response: {e}, structure: {result}")
                        return "⚠️ Не удалось извлечь ответ из нейросети."
                        
        except Exception as e:
            logger.error(f"Connection error to {provider}: {e}")
            return f"⚠️ Не удалось подключиться к серверу нейросети ({type(e).__name__}). Проверьте соединение с интернетом."


# 4. Stream LLM tokens (Server-Sent Events)
async def stream_llm(message: str, history: list):
    """Streams LLM tokens chunk by chunk for OpenRouter/OpenAI/Gemini."""
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()

    if not api_key and provider != "ollama":
        yield (
            "⚠️ <b>Сервер запущен, но не настроен API-ключ.</b><br><br>"
            "Пожалуйста, откройте файл <code>.env</code> в корне папки <code>skyrex-main</code> "
            "и укажите ваш действующий API-ключ в переменной <code>LLM_API_KEY</code>."
        )
        return

    # Setup Defaults
    if provider == "gemini":
        if not model:
            model = "gemini-3.5-flash-lite"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
    else:
        if provider == "openrouter":
            base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
            if not model:
                model = "meta-llama/llama-3.3-70b-instruct:free"
        elif provider == "groq":
            base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
            if not model:
                model = "llama-3.3-70b-versatile"
        elif provider == "ollama":
            base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
            if not model:
                model = "qwen2.5:7b"
        else:
            base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            if not model:
                model = "gpt-4o-mini"
        url = f"{base_url.rstrip('/')}/chat/completions"

    dynamic_context = get_parsed_catalog_context(message)
    system_instruction = build_system_instruction(dynamic_context)
    llm_proxy = get_active_proxy(provider)

    async with aiohttp.ClientSession(trust_env=True) as session:
        try:
            if provider == "gemini":
                contents = []
                for msg in history:
                    role = "user" if msg.get("sender") == "user" else "model"
                    contents.append({
                        "role": role,
                        "parts": [{"text": strip_html_for_history(msg.get("text", ""))}]
                    })
                contents.append({"role": "user", "parts": [{"text": message}]})

                payload = {
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": contents,
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192}
                }
                async with session.post(url, json=payload, proxy=llm_proxy, timeout=75) as resp:
                    if resp.status in (429, 503, 500):
                        err_text = await resp.text()
                        fallback_model = "gemini-3.5-flash-lite" if model != "gemini-3.5-flash-lite" else "gemini-flash-lite-latest"
                        logger.warning(f"Gemini streaming status {resp.status} with {model}, falling back to {fallback_model}...")
                        fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/{fallback_model}:streamGenerateContent?key={api_key}&alt=sse"
                        await asyncio.sleep(1.0)
                        try:
                            async with session.post(fallback_url, json=payload, proxy=llm_proxy, timeout=75) as fb_resp:
                                if fb_resp.status == 200:
                                    async for line_bytes in fb_resp.content:
                                        line = line_bytes.decode('utf-8', errors='ignore').strip()
                                        if not line or not line.startswith("data:"):
                                            continue
                                        data_str = line[5:].strip()
                                        try:
                                            parsed = json.loads(data_str)
                                            candidates = parsed.get("candidates", [])
                                            if candidates:
                                                parts = candidates[0].get("content", {}).get("parts", [])
                                                for part in parts:
                                                    t = part.get("text", "")
                                                    if t:
                                                        yield t
                                        except Exception:
                                            pass
                                    return
                        except Exception as fb_err:
                            logger.error(f"Gemini streaming fallback error: {fb_err}")

                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"Gemini API streaming error ({resp.status}): {err_text}")
                        yield f"⚠️ Ошибка Gemini API ({resp.status}). Проверьте API-ключ."
                        return

                    async for line_bytes in resp.content:
                        line = line_bytes.decode('utf-8', errors='ignore').strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        try:
                            parsed = json.loads(data_str)
                            candidates = parsed.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for part in parts:
                                    t = part.get("text", "")
                                    if t:
                                        yield t
                        except Exception:
                            pass
            else:
                messages = [{"role": "system", "content": system_instruction}]
                for msg in history:
                    role = "user" if msg.get("sender") == "user" else "assistant"
                    messages.append({"role": role, "content": strip_html_for_history(msg.get("text", ""))})
                messages.append({"role": "user", "content": message})

                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2048,
                    "stream": True
                }
                headers = {}
                if provider != "ollama":
                    headers["Authorization"] = f"Bearer {api_key}"
                if provider == "openrouter":
                    headers["HTTP-Referer"] = "https://skyrex.ai"
                    headers["X-Title"] = "Skyrex Computers AI"

                async with session.post(url, json=payload, headers=headers, proxy=llm_proxy, timeout=75) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"{provider.upper()} API streaming error ({resp.status}): {err_text}")
                        yield f"⚠️ Ошибка {provider.upper()} API ({resp.status})."
                        return

                    async for line_bytes in resp.content:
                        line = line_bytes.decode('utf-8', errors='ignore').strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            parsed = json.loads(data_str)
                            choices = parsed.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                t = delta.get("content", "")
                                if t:
                                    yield t
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Stream connection error to {provider}: {e}")
            yield f"⚠️ Ошибка соединения с нейросетью ({type(e).__name__})."

# Optional background price auto-updater (can be enabled via .env)
auto_scraper_enabled = os.getenv("ENABLE_AUTO_SCRAPER", "false").lower() in ("true", "1", "yes")
if auto_scraper_enabled:
    scheduler = BackgroundPriceScheduler(interval_hours=int(os.getenv("SCRAPER_INTERVAL_HOURS", 12)))
    scheduler.start()
    logger.info("Background price scheduler enabled.")

# 4. Request handlers
async def handle_search_price(request):
    """API endpoint for sub-millisecond price lookups by query or category."""
    try:
        query = request.query.get("q", "").strip()
        category = request.query.get("category", "").strip() or None
        shop = request.query.get("shop", "").strip() or None
        max_price_raw = request.query.get("max_price", "").strip()
        max_price = int(max_price_raw) if max_price_raw.isdigit() else None
        limit = min(int(request.query.get("limit", 10)), 50)
        
        results = search_price(query=query, category=category, shop=shop, max_price=max_price, limit=limit)
        return web.json_response({
            "query": query,
            "count": len(results),
            "results": results,
            "formatted": format_price_results(results)
        })
    except Exception as e:
        logger.error(f"Error in handle_search_price: {e}")
        return web.json_response({"error": str(e)}, status=500)


# Security & CORS Middleware: Handles preflight, blocks sensitive files & sets security headers
@web.middleware
async def security_middleware(request, handler):
    origin = request.headers.get("Origin", "*")
    
    # 1. Handle CORS Preflight OPTIONS requests for all API endpoints
    if request.method == "OPTIONS":
        return web.Response(status=204, headers={
            "Access-Control-Allow-Origin": origin if origin else "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS, PUT, DELETE",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With, Accept, Origin",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "86400"
        })

    path = request.path.lower()
    
    # 2. Block attempts to view sensitive system and source files
    blocked_patterns = [
        '.env', '.db', '.py', '.bat', '.sh', '.git', 'bot_db.js',
        'catalog', 'users.db', 'requirements.txt'
    ]
    if any(b in path for b in blocked_patterns) and not path.startswith('/api/'):
        logger.warning(f"Blocked unauthorized access attempt to sensitive file: {request.path} from {request.remote}")
        return web.Response(text="403 Forbidden: Access Denied", status=403)
        
    try:
        response = await handler(request)
    except web.HTTPException as ex:
        response = ex

    # 3. Set hardened security and CORS headers
    response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept, Origin"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Auth Request Handlers
async def handle_auth_register(request):
    """Directly registers a new user with username and password in users.db."""
    try:
        data = await request.json()
        username = (data.get("username") or data.get("login") or "").strip()
        password = data.get("password", "")
        result = register_user(username, password)
        status = 200 if result.get("success") else 400
        return web.json_response(result, status=status)
    except Exception as e:
        logger.error(f"Error in handle_auth_register: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_auth_login(request):
    """Authenticates user with username and password against users.db."""
    try:
        data = await request.json()
        username = (data.get("username") or data.get("login") or "").strip()
        password = data.get("password", "")
        result = login_user(username, password)
        status = 200 if result.get("success") else 401
        return web.json_response(result, status=status)
    except Exception as e:
        logger.error(f"Error in handle_auth_login: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_auth_me(request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else ""
    user = get_user_by_token(token)
    if not user:
        return web.json_response({"authenticated": False}, status=401)
    return web.json_response({"authenticated": True, "user": user})

async def handle_auth_logout(request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else ""
    logout_token(token)
    return web.json_response({"success": True})

async def handle_chat(request):
    try:
        # Rate limit per IP address
        remote_ip = request.headers.get("X-Forwarded-For", request.remote or "unknown").split(",")[0].strip()
        if not check_rate_limit(remote_ip):
            return web.json_response(
                {"response": "⏳ Слишком много запросов. Пожалуйста, подождите минуту перед следующим сообщением."},
                status=429
            )

        # Check authorization token (optional during free beta)
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else ""
        current_user = get_user_by_token(token) if token else None

        data = await request.json()
        message = data.get("message", "").strip()
        history = data.get("history", [])
        wants_stream = bool(data.get("stream", False))
        
        if not message:
            return web.json_response({"response": "Сообщение не может быть пустым."})

        if wants_stream:
            response = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'text/event-stream; charset=utf-8',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Access-Control-Allow-Origin': '*',
                }
            )
            await response.prepare(request)
            try:
                async for chunk in stream_llm(message, history):
                    payload = json.dumps({"chunk": chunk}, ensure_ascii=False)
                    await response.write(f"data: {payload}\n\n".encode('utf-8'))
                await response.write(b"data: [DONE]\n\n")
            except Exception as se:
                logger.error(f"Error during streaming: {se}")
                payload = json.dumps({"error": str(se)}, ensure_ascii=False)
                await response.write(f"data: {payload}\n\n".encode('utf-8'))
            await response.write_eof()
            return response
            
        ai_response = await call_llm(message, history)
        return web.json_response({"response": ai_response})
    except Exception as e:
        logger.error(f"Error handling chat request: {e}")
        err_msg = f"⚠️ Внутренняя ошибка сервера: {str(e)}" if DEBUG else "⚠️ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте снова позже."
        return web.json_response({"response": err_msg}, status=500)

async def handle_index(request):
    return web.FileResponse(os.path.join(PROJECT_ROOT, 'index.html'))

async def handle_safe_static(request):
    """Serves strictly whitelisted client-side scripts and stylesheets."""
    filename = request.match_info.get('filename')
    allowed_files = {
        'style.css': 'style.css',
        'app.js': 'app.js',
        'auth.js': 'auth.js',
        'chat_bot.js': 'chat_bot.js'
    }
    if filename not in allowed_files:
        return web.Response(text="404 Not Found", status=404)
    return web.FileResponse(os.path.join(PROJECT_ROOT, allowed_files[filename]))

# 5. Initialize application
async def init_app():
    app = web.Application(middlewares=[security_middleware])
    
    # API endpoints
    app.router.add_post('/api/chat', handle_chat)
    app.router.add_get('/api/search_price', handle_search_price)
    
    # Real Authentication API
    app.router.add_post('/api/auth/register', handle_auth_register)
    app.router.add_post('/api/auth/login', handle_auth_login)
    app.router.add_get('/api/auth/me', handle_auth_me)
    app.router.add_post('/api/auth/logout', handle_auth_logout)
    
    # Public API for expert catalog & rules
    async def handle_expert_components(request):
        from db.database import get_expert_components
        components = get_expert_components(limit=200)
        return web.json_response({"components": components})

    async def handle_ai_rules(request):
        from db.database import get_ai_rules
        rules = get_ai_rules(active_only=True)
        return web.json_response({"rules": rules})

    app.router.add_get('/api/expert-components', handle_expert_components)
    app.router.add_get('/api/ai-rules', handle_ai_rules)

    # HTML pages
    app.router.add_get('/', handle_index)
    app.router.add_get('/index.html', handle_index)
    
    # Explicitly whitelisted assets ONLY (Never expose project root!)
    app.router.add_get(r'/{filename:(?:style\.css|app\.js|auth\.js|chat_bot\.js)}', handle_safe_static)
    assets_dir = os.path.join(PROJECT_ROOT, 'assets')
    if os.path.exists(assets_dir):
        app.router.add_static('/assets/', path=assets_dir)

    # Background Telegram Admin Bot
    tg_token = os.getenv("TG_BOT_TOKEN", "").strip()
    if tg_token:
        tg_bot = TelegramAdminBot(token=tg_token)
        async def start_tg(app_instance):
            app_instance['tg_bot_task'] = asyncio.create_task(tg_bot.start())
            logger.info("Telegram Admin Bot launched in background.")

        async def stop_tg(app_instance):
            await tg_bot.stop()
            if 'tg_bot_task' in app_instance:
                app_instance['tg_bot_task'].cancel()
                try:
                    await app_instance['tg_bot_task']
                except asyncio.CancelledError:
                    pass
            logger.info("Telegram Admin Bot stopped cleanly.")

        app.on_startup.append(start_tg)
        app.on_cleanup.append(stop_tg)
        
    return app

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting Skyrex AI Server on http://{host}:{port} (Local: http://localhost:{port})...")
    web.run_app(init_app(), host=host, port=port)
