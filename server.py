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
    name_upper = name.upper()
    specs = {
        "socket": None,
        "ram_type": None,
        "psu_watts": None
    }
    
    # Socket detection (case-insensitive, supports all model prefixes and micro-ATX M variants)
    if "AM5" in name_upper or re.search(r'Ryzen\s*(?:5|7|9)\s*(?:7\d{3}|8\d{3}|9\d{3})', name, re.I) or re.search(r'\b(?:X870|B850|B650|A620|X670)', name, re.I):
        specs["socket"] = "AM5"
    elif "AM4" in name_upper or re.search(r'Ryzen\s*(?:3|5|7|9)\s*(?:1\d{3}|2\d{3}|3\d{3}|4\d{3}|5\d{3})', name, re.I) or re.search(r'\b(?:B550|A520|B450|X570|A320)', name, re.I):
        specs["socket"] = "AM4"
    elif "1851" in name or re.search(r'\b(?:Z890|B860)', name, re.I) or "ULTRA 9" in name_upper or "ULTRA 7" in name_upper or "ULTRA 5" in name_upper:
        specs["socket"] = "LGA 1851"
    elif "1700" in name or re.search(r'i[3579]\s*[- ]?(?:12\d{3}|13\d{3}|14\d{3})', name, re.I) or re.search(r'\b(?:B760|Z790|H610|W680|Z690|B660)', name, re.I):
        specs["socket"] = "LGA 1700"
    elif "STR5" in name_upper or "THREADRIPPER" in name_upper:
        specs["socket"] = "sTR5"
    elif "1200" in name or re.search(r'i[3579]\s*[- ]?(?:10\d{3}|11\d{3})', name, re.I) or re.search(r'\b(?:B460|B560|H410|H510|Z490|Z590)', name, re.I):
        specs["socket"] = "LGA 1200"
    elif "1151" in name or re.search(r'i[3579]\s*[- ]?(?:6\d{3}|7\d{3}|8\d{3}|9\d{3})', name, re.I) or re.search(r'\b(?:H110|B250|B360|B365|Z370|Z390)', name, re.I):
        specs["socket"] = "LGA 1151"

    # RAM Type
    if "DDR5" in name_upper:
        specs["ram_type"] = "DDR5"
    elif "DDR4" in name_upper:
        specs["ram_type"] = "DDR4"
    elif "DDR3" in name_upper:
        specs["ram_type"] = "DDR3"
    elif specs["socket"] in ("AM5", "LGA 1851"):
        specs["ram_type"] = "DDR5"
    elif specs["socket"] in ("AM4", "LGA 1200", "LGA 1151"):
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
    
    # If this is a build request with budget, filter out specific results that exceed realistic GPU/core budget
    if budget and is_build_request:
        specific_results = [p for p in specific_results if p.get('price', 0) <= budget]

    cat_items = []
    if is_build_request or budget or len(specific_results) < 5:
        with get_connection() as conn:
            # Dynamic market minimum entry prices queried directly from live catalog.db (no hardcoded numbers)
            market_mins = {}
            for cat in ['cpu', 'gpu', 'motherboard', 'ram', 'ssd', 'psu', 'cooler', 'case']:
                row_min = conn.execute(
                    "SELECT MIN(price) FROM products WHERE category = ? AND price >= 500 AND available = 1",
                    (cat,)
                ).fetchone()
                market_mins[cat] = int(row_min[0]) if (row_min and row_min[0]) else 1000

            total_market_mins = sum(market_mins.values())

            supporting_cats = ['motherboard', 'cooler', 'ram', 'ssd', 'psu', 'case']
            min_supporting = sum(market_mins.get(c, 1000) for c in supporting_cats)

            if budget:
                # Rule 8: Core (GPU + CPU) gets remaining budget after supporting platform frame.
                # In gaming builds, GPU is ~68% of core budget, CPU is ~32% of core budget.
                available_core = max(budget - min_supporting, market_mins.get('cpu', 4500) + market_mins.get('gpu', 2106))
                min_gpu_price = max(int(available_core * 0.25), market_mins.get('gpu', 2106)) if budget >= 50000 else market_mins.get('gpu', 2106)
                max_gpu_price = max(int(available_core * 0.68), market_mins.get('gpu', 2106))
                min_cpu_price = max(int(available_core * 0.10), market_mins.get('cpu', 4500)) if budget >= 50000 else market_mins.get('cpu', 4500)
                max_cpu_price = max(int(available_core * 0.32), market_mins.get('cpu', 4500))

                # Dynamic ceilings for supporting platform components proportional to budget
                max_mb_price = max(int(budget * 0.18), market_mins.get('motherboard', 2500))
                max_ram_price = max(int(budget * 0.15), market_mins.get('ram', 4500))
                max_psu_price = max(int(budget * 0.12), market_mins.get('psu', 3000))
                max_ssd_price = max(int(budget * 0.12), market_mins.get('ssd', 1500))
                max_cooler_price = max(int(budget * 0.08), market_mins.get('cooler', 1000))
                max_case_price = max(int(budget * 0.10), market_mins.get('case', 2500))
            else:
                min_gpu_price = 0
                max_gpu_price = 9999999
                min_cpu_price = 0
                max_cpu_price = 9999999
                max_mb_price = 9999999
                max_ram_price = 9999999
                max_psu_price = 9999999
                max_ssd_price = 9999999
                max_cooler_price = 9999999
                max_case_price = 9999999

            # A. Select Candidate GPUs fitting budget (accessible value first, filter office display adapters)
            gpu_junk_filter = (
                " AND name NOT LIKE '%GT210%' AND name NOT LIKE '%GT 210%' "
                " AND name NOT LIKE '%GT710%' AND name NOT LIKE '%GT 710%' "
                " AND name NOT LIKE '%GT730%' AND name NOT LIKE '%GT 730%' "
                " AND name NOT LIKE '%GT740%' AND name NOT LIKE '%GT 740%' "
                " AND name NOT LIKE '%GT1030%' AND name NOT LIKE '%GT 1030%' "
                " AND name NOT LIKE '%N210%' "
                " AND name NOT LIKE '%CMP40%' AND name NOT LIKE '%CMP 40%' "
                " AND name NOT LIKE '%нерабоч%' AND name NOT LIKE '%под ремонт%' AND name NOT LIKE '%на запчаст%' "
            )
            all_gpus = [dict(r) for r in conn.execute(
                f"SELECT * FROM products WHERE category = 'gpu' AND price >= ? AND price <= ? {gpu_junk_filter} ORDER BY price ASC",
                (min_gpu_price, max_gpu_price)
            ).fetchall()]
            if not all_gpus:
                all_gpus = [dict(r) for r in conn.execute(
                    f"SELECT * FROM products WHERE category = 'gpu' AND price <= ? {gpu_junk_filter} ORDER BY price ASC LIMIT 20",
                    (max_gpu_price,)
                ).fetchall()]
            if not all_gpus:
                all_gpus = [dict(r) for r in conn.execute(
                    f"SELECT * FROM products WHERE category = 'gpu' {gpu_junk_filter} ORDER BY price ASC LIMIT 20"
                ).fetchall()]
            
            # Sample across catalog percentiles up to max_gpu_price (from budget value to top performer)
            if len(all_gpus) > 8:
                step_g = len(all_gpus) - 1
                percentiles_g = [0, step_g // 6, 2 * step_g // 6, 3 * step_g // 6, 4 * step_g // 6, 5 * step_g // 6, step_g]
                raw_gpus = [all_gpus[i] for i in percentiles_g]
            else:
                raw_gpus = all_gpus
            cat_items.extend(enrich_and_rank_products(raw_gpus, expert_components, limit=8))

            # B. Select Candidate CPUs fitting budget (stepped spread, standalone CPUs only)
            cpu_filter_threadripper = " AND name NOT LIKE '%Threadripper%' " if (not budget or budget < 1000000) else ""
            cpu_filter_bundle = (
                " AND name NOT LIKE '%комплект%' "
                " AND name NOT LIKE '%komplekt%' "
                " AND name NOT LIKE '%материн%' "
                " AND name NOT LIKE '%плата%' "
                " AND name NOT LIKE '%plata%' "
                " AND name NOT LIKE '%motherboard%' "
                " AND name NOT LIKE '%b450%' "
                " AND name NOT LIKE '%b550%' "
                " AND name NOT LIKE '%b650%' "
                " AND name NOT LIKE '%b760%' "
                " AND name NOT LIKE '%b850%' "
                " AND name NOT LIKE '%h610%' "
                " AND name NOT LIKE '%a620%' "
                " AND name NOT LIKE '%z790%' "
                " AND name NOT LIKE '%x870%' "
                " AND name NOT LIKE '%с кулером%' "
                " AND name NOT LIKE '%s kulerom%' "
                " AND name NOT LIKE '%snowman%' "
                " AND name NOT LIKE '%vodyanka%' "
                " AND name NOT LIKE '%bashnya%' "
                " AND name NOT LIKE '%сборк%' "
                " AND name NOT LIKE '%sbork%' "
                " AND name NOT LIKE '%игровой пк%' "
                " AND name NOT LIKE '%+%' "
                " AND name NOT LIKE '%32gb%' "
                " AND name NOT LIKE '%16gb%' "
                " AND name NOT LIKE '%ddr5%' "
                " AND name NOT LIKE '%ddr4%' "
            )

            all_cpus = [dict(r) for r in conn.execute(
                f"SELECT * FROM products WHERE category = 'cpu' AND price >= ? AND price <= ? {cpu_filter_threadripper} {cpu_filter_bundle} ORDER BY price ASC",
                (min_cpu_price, max_cpu_price)
            ).fetchall()]
            if not all_cpus:
                all_cpus = [dict(r) for r in conn.execute(
                    f"SELECT * FROM products WHERE category = 'cpu' AND price <= ? {cpu_filter_threadripper} {cpu_filter_bundle} ORDER BY price ASC",
                    (max_cpu_price,)
                ).fetchall()]
            if not all_cpus:
                all_cpus = [dict(r) for r in conn.execute(f"SELECT * FROM products WHERE category = 'cpu' {cpu_filter_threadripper} {cpu_filter_bundle} ORDER BY price ASC LIMIT 20").fetchall()]

            if len(all_cpus) > 7:
                step_c = len(all_cpus) - 1
                percentiles_c = [0, step_c // 5, 2 * step_c // 5, 3 * step_c // 5, 4 * step_c // 5, step_c]
                raw_cpus = [all_cpus[i] for i in percentiles_c]
            else:
                raw_cpus = all_cpus

            selected_cpus = enrich_and_rank_products(raw_cpus, expert_components, limit=6)
            cat_items.extend(selected_cpus)

            # C. Detect Sockets of selected candidate CPUs to guarantee 100% MOTHERBOARD COMPATIBILITY
            candidate_sockets = set()
            for c in selected_cpus:
                specs = detect_hardware_specs(c)
                if specs["socket"]:
                    candidate_sockets.add(specs["socket"])

            # D. Select Motherboards matching candidate sockets (partitioned per socket to guarantee 100% compatibility)
            selected_mbs = []
            target_sockets_list = list(candidate_sockets) if candidate_sockets else ["AM4", "LGA 1700"]
            for target_socket in target_sockets_list:
                socket_kw = []
                if target_socket == "AM5":
                    socket_kw = ["%B650%", "%A620%", "%X670%", "%B850%", "%X870%", "%AM5%"]
                elif target_socket == "AM4":
                    socket_kw = ["%B450%", "%B550%", "%A520%", "%X570%", "%AM4%"]
                elif target_socket == "LGA 1700":
                    socket_kw = ["%H610%", "%B760%", "%Z790%", "%Z690%", "%1700%"]
                elif target_socket == "LGA 1200":
                    socket_kw = ["%H410%", "%H510%", "%B460%", "%B560%", "%1200%"]

                if socket_kw:
                    sql_kw = " OR ".join(["name LIKE ?"] * len(socket_kw))
                    rows = [dict(r) for r in conn.execute(
                        f"SELECT * FROM products WHERE category = 'motherboard' AND price <= ? AND ({sql_kw}) ORDER BY price ASC LIMIT 20",
                        [max_mb_price] + socket_kw
                    ).fetchall()]
                    if not rows:
                        rows = [dict(r) for r in conn.execute(
                            f"SELECT * FROM products WHERE category = 'motherboard' AND ({sql_kw}) ORDER BY price ASC LIMIT 20",
                            socket_kw
                        ).fetchall()]
                    compatible = []
                    for m in rows:
                        specs = detect_hardware_specs(m)
                        if specs["socket"] == target_socket or not specs["socket"]:
                            m["detected_socket"] = target_socket
                            m["detected_ram"] = specs["ram_type"] or ("DDR5" if target_socket == "AM5" else "DDR4")
                            compatible.append(m)
                    selected_mbs.extend(enrich_and_rank_products(compatible, expert_components, limit=3, sort_by_price_desc=False))

            cat_items.extend(selected_mbs)

            # E. Detect RAM Types required by selected compatible motherboards
            required_ram_types = set(mb.get("detected_ram") for mb in selected_mbs if mb.get("detected_ram"))
            if not required_ram_types:
                required_ram_types = {"DDR4"}

            ram_junk_filter = (
                " AND name NOT LIKE '%SODIMM%' AND name NOT LIKE '%SO-DIMM%' AND name NOT LIKE '%ноутбук%' "
                " AND name NOT LIKE '%для ноут%' AND name NOT LIKE '%неисправн%' AND name NOT LIKE '%под заказ%' "
                " AND name NOT LIKE '%связка%' AND name NOT LIKE '%комплект с%' AND name NOT LIKE '%комплект материн%' "
            )

            def get_ram_capacity(name):
                m_cap = re.search(r'(\d+)\s*(?:гб|gb)\b', name, re.I)
                if m_cap:
                    return int(m_cap.group(1))
                return 16

            def is_clean_ram(name: str) -> bool:
                nl = name.lower()
                bad = ["sodimm", "so-dimm", "ноутбук", "для ноут", "неисправн", "под заказ", "связка", "комплект с", "на запчаст", "на запчасти"]
                return not any(b in nl for b in bad)

            selected_rams = []
            for r_type in required_ram_types:
                kw = "%ddr5%" if r_type == "DDR5" else "%ddr4%"
                rows = [dict(r) for r in conn.execute(
                    f"SELECT * FROM products WHERE category = 'ram' AND name LIKE ? AND price <= ? ORDER BY price ASC LIMIT 30",
                    (kw, max_ram_price)
                ).fetchall()]
                if not rows:
                    rows = [dict(r) for r in conn.execute(
                        f"SELECT * FROM products WHERE category = 'ram' AND name LIKE ? ORDER BY price ASC LIMIT 30",
                        (kw,)
                    ).fetchall()]
                filtered_r = []
                for r in rows:
                    if not is_clean_ram(r.get("name", "")):
                        continue
                    specs = detect_hardware_specs(r)
                    cap = get_ram_capacity(r.get("name", ""))
                    r["detected_capacity"] = cap
                    r["detected_ram"] = r_type
                    filtered_r.append(r)
                # Sort: largest capacity first, then lowest price (maximum volume per ruble)
                filtered_r.sort(key=lambda x: (-x.get("detected_capacity", 16), x.get("price", 0)))
                selected_rams.extend(enrich_and_rank_products(filtered_r, expert_components, limit=3, sort_by_price_desc=None))

            cat_items.extend(selected_rams)

            # F. Select PSUs fitting budget (whitelisted customer models: Powercase, GamerStorm PF >=600W, 1STPLAYER NGDP)
            psu_whitelist = """
                AND (
                    (name LIKE '%Powercase%' AND (name LIKE '%PW500%' OR name LIKE '%PW600%' OR name LIKE '%PW700%' OR name LIKE '%PW 500%' OR name LIKE '%PW 600%' OR name LIKE '%PW 700%' OR name LIKE '%PW-500%' OR name LIKE '%PW-600%' OR name LIKE '%PW-700%'))
                    OR (name LIKE '%GAMERSTORM%' AND (name LIKE '%PF600%' OR name LIKE '%PF650%' OR name LIKE '%PF700%' OR name LIKE '%PF750%' OR name LIKE '%PF800%' OR name LIKE '%PF850%' OR name LIKE '%PF 600%' OR name LIKE '%PF 650%' OR name LIKE '%PF 700%' OR name LIKE '%PF 750%' OR name LIKE '%PF 800%' OR name LIKE '%PF 850%' OR name LIKE '%PF%X%' OR name LIKE '%PF%D%'))
                    OR (name LIKE '%1STPLAYER%' AND name LIKE '%NGDP%' AND name NOT LIKE '%1200%')
                )
            """
            raw_psus = [dict(r) for r in conn.execute(
                f"SELECT * FROM products WHERE category = 'psu' AND price <= ? {psu_whitelist} ORDER BY price ASC LIMIT 20",
                (max_psu_price,)
            ).fetchall()]
            if not raw_psus:
                raw_psus = [dict(r) for r in conn.execute(f"SELECT * FROM products WHERE category = 'psu' {psu_whitelist} ORDER BY price ASC LIMIT 20").fetchall()]
            diverse_psus = []
            seen_p_ids = set()
            for p in sorted(raw_psus, key=lambda x: x.get("price", 0)):
                if p["id"] not in seen_p_ids:
                    diverse_psus.append(p)
                    seen_p_ids.add(p["id"])
                    if len(diverse_psus) >= 2:
                        break
            for p in enrich_and_rank_products(raw_psus, expert_components, limit=5):
                if p["id"] not in seen_p_ids:
                    diverse_psus.append(p)
                    seen_p_ids.add(p["id"])
                    if len(diverse_psus) >= 5:
                        break
            cat_items.extend(diverse_psus if diverse_psus else enrich_and_rank_products(raw_psus, expert_components, limit=5))

            # G. Select SSDs fitting budget (strictly authentic M.2 NVMe, no junk/broken/multi-item ads)
            ssd_filter = (
                " AND (name LIKE '%m.2%' OR name LIKE '%m2%' OR name LIKE '%nvme%') "
                " AND name NOT LIKE '%sata%' "
                " AND name NOT LIKE '%msata%' "
                " AND name NOT LIKE '%нерабоч%' "
                " AND name NOT LIKE '%под ремонт%' "
                " AND name NOT LIKE '%на запчаст%' "
                " AND name NOT LIKE '%диски%' "
                " AND name NOT LIKE '%m225%' "
                " AND name NOT LIKE '%ngff%' "
                " AND name NOT LIKE '%/ 256%' "
                " AND name NOT LIKE '%/ 512%' "
            )
            cap_filter = " AND (name LIKE '%512%' OR name LIKE '%500%' OR name LIKE '%1tb%' OR name LIKE '%1 tb%' OR name LIKE '%1тб%' OR name LIKE '%1 тб%' OR name LIKE '%1000%' OR name LIKE '%1024%') " if (budget and budget >= 50000) else ""

            raw_ssds = [dict(r) for r in conn.execute(
                f"SELECT * FROM products WHERE category = 'ssd' {ssd_filter} {cap_filter} AND price <= ? ORDER BY price ASC LIMIT 25",
                (max_ssd_price,)
            ).fetchall()]
            if not raw_ssds:
                raw_ssds = [dict(r) for r in conn.execute(f"SELECT * FROM products WHERE category = 'ssd' {ssd_filter} AND price <= ? ORDER BY price ASC LIMIT 25", (max_ssd_price,)).fetchall()]
            if not raw_ssds:
                raw_ssds = [dict(r) for r in conn.execute(f"SELECT * FROM products WHERE category = 'ssd' {ssd_filter} ORDER BY price ASC LIMIT 25").fetchall()]

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

            min_ssd_cap = 512 if (budget and budget >= 50000) else 256
            valid_ssds = [
                s for s in raw_ssds 
                if (s.get("detected_capacity", 0) >= min_ssd_cap and (min_ssd_cap < 512 or re.search(r'(?:512|500|1000|1024|1\s*тб|1\s*tb)', s.get("name", ""), re.I)))
            ]
            if not valid_ssds:
                valid_ssds = raw_ssds

            # Sort candidate SSDs: highest capacity first, then lowest price (maximum volume for lowest price)
            ranked_ssds = sorted(valid_ssds, key=lambda x: (-x["detected_capacity"], x.get("price", 0)))

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
            for s in sorted(valid_ssds, key=lambda x: x.get("price", 0)):
                if s["id"] not in seen_ids:
                    diverse_ssds.append(s)
                    seen_ids.add(s["id"])
                    if len(diverse_ssds) >= 6:
                        break

            cat_items.extend(enrich_and_rank_products(diverse_ssds, expert_components, limit=6, sort_by_price_desc=None))

            # H. Select Coolers fitting budget
            cooler_filter = (
                "WHERE category = 'cooler' "
                "AND name NOT LIKE '%звуков%' AND url NOT LIKE '%zvukovye_karty%' AND name NOT LIKE '%audio%' "
                "AND url NOT LIKE '%videokarty%' AND name NOT LIKE '%geforce%' AND name NOT LIKE '%radeon%' "
                "AND name NOT LIKE '%rtx%' AND name NOT LIKE '%gtx%'"
            )
            min_cooler_price = 1400 if (budget and budget >= 70000) else market_mins.get('cooler', 683)
            raw_coolers = [dict(r) for r in conn.execute(
                f"SELECT * FROM products {cooler_filter} AND price >= ? AND price <= ? ORDER BY price ASC LIMIT 20",
                (min_cooler_price, max_cooler_price)
            ).fetchall()]
            if not raw_coolers:
                raw_coolers = [dict(r) for r in conn.execute(
                    f"SELECT * FROM products {cooler_filter} AND price <= ? ORDER BY price ASC LIMIT 20",
                    (max_cooler_price,)
                ).fetchall()]
            cat_items.extend(enrich_and_rank_products(raw_coolers, expert_components, limit=5, sort_by_price_desc=False))

            # I. Select Cases directly from catalog (purely from parsed products, no requirements)
            raw_cases = [dict(r) for r in conn.execute(
                "SELECT * FROM products WHERE category = 'case' AND price <= ? ORDER BY price ASC LIMIT 20",
                (max_case_price,)
            ).fetchall()]
            if not raw_cases:
                raw_cases = [dict(r) for r in conn.execute(
                    "SELECT * FROM products WHERE category = 'case' ORDER BY price ASC LIMIT 20"
                ).fetchall()]
            if raw_cases:
                cat_items.extend(enrich_and_rank_products(raw_cases, expert_components, limit=5, sort_by_price_desc=False))

    all_products = specific_results + [p for p in cat_items if not any(x['id'] == p['id'] for x in specific_results)]
    
    if all_products:
        budget_header = f" ПОД БЮДЖЕТ {budget:,} РУБ" if budget else ""
        context_parts.append(f"=== АКТУАЛЬНЫЕ ЦЕНЫ И НАЛИЧИЕ ИЗ КАТАЛОГА (АВИТО, WILDBERRIES, ОНЛАЙНТРЕЙД){budget_header} ===")
        if budget:
            context_parts.append(
                f"🧠 ОБЯЗАТЕЛЬНЫЙ ЭТАП ПРЕДВАРИТЕЛЬНОГО РАСЧЕТА И АНАЛИЗА (В УМЕ ПЕРЕД ВЫДАЧЕЙ ОТВЕТА):\n"
                f"1. ПРОВЕРКА СОВМЕСТИМОСТИ СОКЕТА И ПЛАТФОРМЫ:\n"
                f"   - Определи сокет выбранного процессора (например, AM4, AM5, LGA1700).\n"
                f"   - Выбирай материнскую плату ИСКЛЮЧИТЕЛЬНО на том же сокете (для AM4 — строго AM4: A520/B450/B550; для AM5 — строго AM5: B650/A620; для LGA1700 — строго H610/B760)!\n"
                f"   - Поколение оперативной памяти ОБЯЗАНО в точности совпадать с материнской платой (DDR4 к DDR4, DDR5 к DDR5)!\n\n"
                f"2. ДИНАМИЧЕСКИЙ МАТЕМАТИЧЕСКИЙ РАСЧЕТ ОСТАТКА НА ВИДЕОКАРТУ:\n"
                f"   - Сложи реальные актуальные цены 7 базовых компонентов из переданного каталога:\n"
                f"     База = Цена(Процессор) + Цена(Материнская плата) + Цена(Кулер) + Цена(ОЗУ) + Цена(SSD) + Цена(Блок питания) + Цена(Корпус).\n"
                f"   - Вычисли максимально допустимый остаток бюджета на видеокарту: Доступно_на_GPU = {budget:,} руб - База.\n"
                f"   - Выбери из каталога видеокарту, цена которой СТРОГО МЕНЬШЕ или РАВНА полученному остатку (Цена(GPU) <= Доступно_на_GPU)!\n"
                f"   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО брать видеокарту дороже вычисленного остатка, иначе сумма превысит бюджет!\n\n"
                f"3. ИТОГОВАЯ МАТЕМАТИЧЕСКАЯ ПРОВЕРКА:\n"
                f"   - В сборке ОБЯЗАНЫ присутствовать строго ВСЕ 8 пронумерованных компонентов: 1. Процессор, 2. Материнская плата, 3. Кулер, 4. Память, 5. Видеокарта, 6. SSD, 7. Блок питания, 8. Корпус!\n"
                f"   - Точная сумма ВСЕХ 8 позиций ОБЯЗАНА БЫТЬ строго меньше или равна {budget:,} руб (Сумма <= {budget:,} руб)!\n"
                f"   - В строке 'Точная суммарная стоимость:' выведи математически точную сумму цен всех 8 выбранных позиций.\n"
                f"   - КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО превышать этот лимит даже на 1 рубль, начинать пересчитывать сборку на ходу ('Стоп, пересчитываем...') или писать в примечании оправдания!\n"
                f"   - Сразу выведи ОДИН идеальный вариант, который строго укладывается в {budget:,} руб, без ошибок в арифметике и без повторных пересчётов!\n\n"
                f"4. СТРОГИЕ ИСТОЧНИКИ КОМПЛЕКТУЮЩИХ (согласно регламенту Skyrex):\n"
                f"   - Видеокарты: Авито (Б/У) или Wildberries\n"
                f"   - Оперативная память: Авито (Б/У) или Wildberries\n"
                f"   - Процессоры: Wildberries или Авито (Б/У)\n"
                f"   - SSD: Wildberries, Авито (Б/У) или ОнлайнТрейд\n"
                f"   - Материнские платы: Wildberries, Авито (Б/У) или DNS\n"
                f"   - Блоки питания: ОнлайнТрейд или Wildberries (только модели Powercase PW, GamerStorm PF600X+, 1stPlayer NGDP — обычные DeepCool не использовать)\n"
                f"   - Кулеры для процессоров: ОнлайнТрейд или Wildberries\n"
                f"   - Корпус: ОнлайнТрейд или Wildberries (выбирай реальную модель корпуса из каталога)"
            )
        if budget and budget < 35000:
            context_parts.append(
                f"⚠️ ПРАВИЛО УЛЬТРАНИЗКОГО БЮДЖЕТА ({budget:,} РУБ):\n"
                f"1. В бюджете до 35 000 руб. собрать ПК из новых магазинных комплектующих невозможно (одна плата и память съедят бюджет).\n"
                f"2. ПРАВИЛО ЧЕСТНОГО БЮДЖЕТА: КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО говорить во вступлении 'Вот сборка под ваш бюджет {budget:,} руб.', а затем насчитывать сумму в 40 000 руб.!\n"
                f"   - Либо собери ПК ПОЛНОСТЬЮ на проверенном Б/У рынке (Авито) со ссылками на поиск Авито, чтобы итоговая сумма была ровно <= {budget:,} руб. (например: Ryzen 5 2600 + A320 + RX 580 8GB + 16GB DDR4 + БП + SSD = ровно до 20 000 руб.)!\n"
                f"   - Либо СРАЗУ в первой же строчке честно скажи клиенту: 'В бюджете {budget:,} руб. современную платформу i3/Ryzen собрать невозможно, минимальный порог для неё — около 35 000 – 40 000 руб. Вот оптимальная конфигурация на 40 000 руб...'."
            )
        # Partition into category buckets
        cpus = [p for p in all_products if p.get('category') == 'cpu']
        gpus = [p for p in all_products if p.get('category') == 'gpu']
        mbs = [p for p in all_products if p.get('category') == 'motherboard']
        rams = [p for p in all_products if p.get('category') == 'ram']
        psus = [p for p in all_products if p.get('category') == 'psu']
        ssds = [p for p in all_products if p.get('category') == 'ssd']
        coolers = [p for p in all_products if p.get('category') == 'cooler']
        cases = [p for p in all_products if p.get('category') == 'case']

        def format_product_line(p):
            specs = detect_hardware_specs(p)
            spec_tags = []
            if specs["socket"]:
                socket_platform = ""
                if specs["socket"] in ("AM4", "AM5"):
                    socket_platform = " (AMD Ryzen)"
                elif specs["socket"] in ("LGA 1700", "LGA 1851", "LGA 1200"):
                    socket_platform = " (Intel Core)"
                spec_tags.append(f"Сокет: {specs['socket']}{socket_platform}")
            if specs["ram_type"]:
                spec_tags.append(f"Память: {specs['ram_type']}")
            if specs["psu_watts"]:
                spec_tags.append(f"Мощность: {specs['psu_watts']}W")
            tag_str = f" [{ ' | '.join(spec_tags) }]" if spec_tags else ""

            price_str = f"{p['price']:,} руб".replace(",", " ")
            old_str = f" (старая цена: {p['old_price']:,} руб)".replace(",", " ") if p.get('old_price') else ""
            search_url = make_marketplace_search_url(p.get('shop', ''), p['name'])
            return f"- [{p.get('shop', 'ОнлайнТрейд')}] {p['name']}. Цена: {price_str}{old_str}{tag_str}. Ссылка: {search_url}"

        # 1. CPUs
        if cpus:
            context_parts.append("\n=== 1. ПРОЦЕССОРЫ (CPU) ===")
            for p in cpus[:6]:
                context_parts.append(format_product_line(p))

        # 2. Motherboards partitioned by platform
        mbs_am5 = [m for m in mbs if m.get("detected_socket") == "AM5"]
        mbs_am4 = [m for m in mbs if m.get("detected_socket") == "AM4"]
        mbs_lga1700 = [m for m in mbs if m.get("detected_socket") == "LGA 1700"]
        mbs_other = [m for m in mbs if m not in mbs_am5 and m not in mbs_am4 and m not in mbs_lga1700]

        if mbs_am5:
            context_parts.append("\n=== 2. МАТЕРИНСКИЕ ПЛАТЫ ДЛЯ AMD RYZEN AM5 (СТРОГО ДЛЯ CPU НА СОКЕТЕ AM5 И ПАМЯТИ DDR5) ===")
            for p in mbs_am5[:3]:
                context_parts.append(format_product_line(p))

        if mbs_am4:
            context_parts.append("\n=== 3. МАТЕРИНСКИЕ ПЛАТЫ ДЛЯ AMD RYZEN AM4 (СТРОГО ДЛЯ CPU НА СОКЕТЕ AM4 И ПАМЯТИ DDR4) ===")
            for p in mbs_am4[:3]:
                context_parts.append(format_product_line(p))

        if mbs_lga1700:
            context_parts.append("\n=== 4. МАТЕРИНСКИЕ ПЛАТЫ ДЛЯ INTEL LGA 1700 ===")
            for p in mbs_lga1700[:3]:
                context_parts.append(format_product_line(p))

        if mbs_other and not (mbs_am5 or mbs_am4 or mbs_lga1700):
            context_parts.append("\n=== МАТЕРИНСКИЕ ПЛАТЫ ===")
            for p in mbs_other[:3]:
                context_parts.append(format_product_line(p))

        # 3. RAM partitioned by generation
        rams_ddr5 = [r for r in rams if r.get("detected_ram") == "DDR5"]
        rams_ddr4 = [r for r in rams if r.get("detected_ram") == "DDR4"]
        rams_other = [r for r in rams if r not in rams_ddr5 and r not in rams_ddr4]

        if rams_ddr5:
            context_parts.append("\n=== 5. ОПЕРАТИВНАЯ ПАМЯТЬ DDR5 (СТРОГО ДЛЯ ПЛАТФОРМЫ AM5 И ПЛАТ LGA 1700 DDR5) ===")
            for p in rams_ddr5[:3]:
                context_parts.append(format_product_line(p))

        if rams_ddr4:
            context_parts.append("\n=== 6. ОПЕРАТИВНАЯ ПАМЯТЬ DDR4 (СТРОГО ДЛЯ ПЛАТФОРМЫ AM4 И ПЛАТ LGA 1700 DDR4) ===")
            for p in rams_ddr4[:3]:
                context_parts.append(format_product_line(p))

        if rams_other and not (rams_ddr5 or rams_ddr4):
            context_parts.append("\n=== ОПЕРАТИВНАЯ ПАМЯТЬ ===")
            for p in rams_other[:3]:
                context_parts.append(format_product_line(p))

        # 4. GPUs
        if gpus:
            context_parts.append("\n=== 7. ВИДЕОКАРТЫ (GPU) ===")
            for p in gpus[:8]:
                context_parts.append(format_product_line(p))

        # 5. SSDs
        if ssds:
            context_parts.append("\n=== 8. НАКОПИТЕЛИ SSD M.2 NVMe ===")
            for p in ssds[:5]:
                context_parts.append(format_product_line(p))

        # 6. PSUs
        if psus:
            context_parts.append("\n=== 9. БЛОКИ ПИТАНИЯ (PSU: GAMERSTORM / POWERCASE / 1STPLAYER NGDP) ===")
            for p in psus[:4]:
                context_parts.append(format_product_line(p))

        # 7. Coolers
        if coolers:
            context_parts.append("\n=== 10. КУЛЕРЫ ДЛЯ ПРОЦЕССОРА ===")
            for p in coolers[:4]:
                context_parts.append(format_product_line(p))

        # 8. Cases
        if cases:
            context_parts.append("\n=== 11. КОРПУСА ДЛЯ ПК ===")
            for p in cases[:4]:
                context_parts.append(format_product_line(p))

    return "\n".join(context_parts)

def make_marketplace_search_url(shop: str, name: str) -> str:
    """Формирует универсальную ссылку на поисковую строку маркетплейса с введенным названием компонента."""
    clean_name = re.sub(r'<[^>]+>', '', name).strip()
    clean_name = re.sub(r'(?i)\(б/у\)|б/у', '', clean_name).strip()
    clean_name = re.sub(r'(?i)\b(компьютерный|компьютерная|компьютерное|для компьютера|для пк)\b', '', clean_name)
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    if not clean_name:
        clean_name = "комплектующие для пк"

    encoded = urllib.parse.quote_plus(clean_name)
    shop_lower = (shop or "").lower()

    if "wildberries" in shop_lower or "вайлдберриз" in shop_lower:
        return f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded}"
    elif "онлайн" in shop_lower or "online" in shop_lower:
        return f"https://www.onlinetrade.ru/catalogue/?query={encoded}"
    elif "dns" in shop_lower or "днс" in shop_lower:
        return f"https://www.dns-shop.ru/search/?q={encoded}"
    else:
        return f"https://www.avito.ru/all?q={encoded}"

def clean_single_final_build(raw: str) -> str:
    """Гарантирует, что ответ содержит ровно ОДНУ чистовую конфигурацию,
    срезая любые промежуточные черновые попытки ('Ой, секунду! Это превышает...', 'Давайте пересоберем...').
    """
    if not raw:
        return raw

    pattern = re.compile(r'(?:<br\s*/?>|\n|^)\s*(?:<li>)?\s*(?:<b>)?\s*1\.\s*(?:<b>)?\s*(?:Процессор|CPU)', re.IGNORECASE)
    matches = list(pattern.finditer(raw))
    if len(matches) <= 1:
        return raw

    first_match = matches[0]
    last_match = matches[-1]

    intro = raw[:first_match.start()].strip()
    intro = re.sub(r'(?:<br\s*/?>|\n)*\s*(?:Вот|Ниже|Конфигурация).*?:\s*$', '', intro, flags=re.IGNORECASE | re.DOTALL).strip()
    final_build = raw[last_match.start():].strip()

    return f"{intro}\n\n<b>Вот оптимальная конфигурация ПК под ваш бюджет:</b>\n{final_build}"

def sync_exact_total_sum(text: str) -> str:
    """Парсит цены из всех позиций сборки (Процессор, Плата, Кулер, Память, Видеокарта, SSD, БП, Корпус)
    и заменяет строку 'Точная суммарная стоимость:' на математически точную сумму без галлюцинаций.
    """
    if not text:
        return text

    # Ищем строки нумерованных позиций сборки: например '1. Процессор ... — 10 800 руб.'
    # Поддерживаем как разделение по переводам строк, так и по <br> / <li>
    normalized = re.sub(r'<\/?(?:li|ul|ol)[^>]*>', '\n', text)
    normalized = re.sub(r'<br\s*\/?>', '\n', normalized)
    lines = normalized.split('\n')
    item_prices = []

    item_pattern = re.compile(
        r'^\s*(\d+)[\.\)]\s*(?:<b>)?\s*(.*?)\s*(?:—|–|-)\s*([\d\s\xa0]{3,})\s*(?:руб|₽)',
        re.IGNORECASE
    )

    for line in lines:
        line_clean = line.strip()
        m = item_pattern.search(line_clean)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 8:
                raw_p = re.sub(r'[\s\xa0]', '', m.group(3))
                if raw_p.isdigit():
                    p_val = int(raw_p)
                    if 500 <= p_val <= 300000:
                        item_prices.append((num, p_val))

    # Если распознано минимум 4 компонента сборки, считаем точную сумму
    if len(item_prices) >= 4:
        unique_pos = {}
        for num, p in item_prices:
            unique_pos[num] = p

        exact_sum = sum(unique_pos.values())
        formatted_sum = f"{exact_sum:,} руб.".replace(",", " ")

        total_regex = re.compile(
            r'((?:<b>)?\s*(?:Точная суммарная стоимость|Итоговая стоимость|Суммарная стоимость|Итого|Стоимость сборки)[^:\n<]*:(?:<\/b>)?\s*)(?:<b>)?([^\n<]+)(?:<\/b>)?',
            re.IGNORECASE
        )
        if total_regex.search(text):
            text = total_regex.sub(rf'\g<1><b>{formatted_sum}</b>', text)
        else:
            text += f"\n\n<b>Точная суммарная стоимость:</b> {formatted_sum}"

    return text

def clean_marketplace_links(text: str) -> str:
    """Гарантирует, что ВСЕ ссылки (Авито, Wildberries, ОнлайнТрейд, DNS) ведут на страницу поиска
    по названию компонента в поисковой строке, а не на прямые/устаревшие карточки товаров.
    Также синхронизирует итоговую сумму с математически точным расчетом позиций.
    """
    if not text:
        return text

    text = clean_single_final_build(text)

    # 1. Заменяем любые упоминания 'Deepcool GAMERSTORM' / 'DeepCool GAMERSTORM' / 'DeepCool PF...' на 'GamerStorm'
    text = re.sub(r'(?i)deepcool\s+gamerstorm', 'GamerStorm', text)
    text = re.sub(r'(?i)deepcool\s*(pf\d+[xd]?)', r'GamerStorm \1', text)

    # 2. Преобразование Markdown-ссылок [текст](url) в чистый HTML с поисковой ссылкой
    def md_link_replacer(match):
        title = match.group(1)
        url = match.group(2)
        shop = "Авито"
        if "wildberries.ru" in url:
            shop = "Wildberries"
        elif "onlinetrade.ru" in url:
            shop = "ОнлайнТрейд"
        elif "dns-shop.ru" in url:
            shop = "DNS"
        search_url = make_marketplace_search_url(shop, title)
        return f"<a href='{search_url}' target='_blank'>{title}</a>"

    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', md_link_replacer, text)

    # 3. Коррекция HTML-ссылок <a href='...'>текст</a>
    def html_link_replacer(match):
        full_tag = match.group(0)
        href = match.group(1)
        inner_text = match.group(2)

        shop = "Авито"
        if "wildberries.ru" in href:
            shop = "Wildberries"
        elif "onlinetrade.ru" in href:
            shop = "ОнлайнТрейд"
        elif "dns-shop.ru" in href:
            shop = "DNS"
        elif "avito.ru" in href:
            shop = "Авито"
        else:
            return full_tag

        search_url = make_marketplace_search_url(shop, inner_text)
        return f"<a href='{search_url}' target='_blank'>{inner_text}</a>"

    html_a_pattern = re.compile(r"<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    text = html_a_pattern.sub(html_link_replacer, text)

    # 4. Предотвращение слипания ключевых блоков текста (Точная сумма, Примечание, Советы по проверке)
    text = re.sub(
        r'([^\n>])\s*(<b>\s*)?(Точная суммарная стоимость|Примечание эксперта|Примечание|При покупке комплектующих|При покупке с Авито|Остаток от бюджета)',
        r'\1<br><br>\2\3',
        text,
        flags=re.IGNORECASE
    )
    # Предотвращение слипания нумерованных позиций сборки (руб.2. Материнская плата -> руб.<br>2. Материнская плата)
    text = re.sub(r'([^\n>])\s*(\b\d+\.\s*(?:<b>)?[А-ЯA-Z])', r'\1<br>\2', text)
    # Предотвращение слипания заголовка конфигурации (.Конфигурация -> .<br><br>Конфигурация)
    text = re.sub(r'([^\n>])\s*(Конфигурация ПК под ваш бюджет|Вот сбалансированная|Вот оптимальная)', r'\1<br><br>\2', text, flags=re.IGNORECASE)

    # 5. Математически точная синхронизация итоговой суммы
    text = sync_exact_total_sum(text)

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

    catalog_text = "=== МЕДИАННЫЕ РЫНОЧНЫЕ ЦЕНЫ КОМПЛЕКТУЮЩИХ (АВИТО Б/У) ===\n\n"
    for component in components:
        comp_name = component.get('componentname', 'Без названия')
        avito_query = urllib.parse.quote_plus(comp_name)
        avito_url = f"https://www.avito.ru/all?q={avito_query}"
        catalog_text += (
            f"- {comp_name} "
            f"({component.get('type', 'other').upper()}). "
        )
        if component.get('price'):
            catalog_text += f"Медианная рыночная цена: {component['price']} руб. "
        if component.get("minprice"):
            catalog_text += f"(Минимальная цена: {component['minprice']} руб). "
        catalog_text += f"Ссылка на поиск Авито: {avito_url}."
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
            model = "gemini-flash-lite-latest"
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
                        "maxOutputTokens": 8192,
                        "thinkingConfig": {"thinkingBudget": 512}
                    }
                }
                
                models_to_try = [model]
                for fb in ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-1.5-flash"]:
                    if fb not in models_to_try:
                        models_to_try.append(fb)

                last_error = ""
                for try_model in models_to_try:
                    try_url = f"https://generativelanguage.googleapis.com/v1beta/models/{try_model}:generateContent?key={api_key}"
                    for attempt in range(2):
                        logger.info(f"Sending request to Gemini API (Model: {try_model}, Attempt: {attempt+1}, Proxy: {llm_proxy or 'direct'})...")
                        try:
                            async with session.post(try_url, json=payload, proxy=llm_proxy, timeout=75) as resp:
                                if resp.status == 200:
                                    result = await resp.json()
                                    candidates = result.get("candidates", [])
                                    if candidates:
                                        parts = candidates[0].get("content", {}).get("parts", [])
                                        if parts and "text" in parts[0]:
                                            return clean_marketplace_links(parts[0]["text"])
                                last_error = f"Status {resp.status}"
                                if resp.status in (429, 503, 500):
                                    await asyncio.sleep(1.5)
                                    continue
                                break
                        except Exception as req_err:
                            last_error = str(req_err)
                            await asyncio.sleep(1.0)

                return f"⚠️ Сервер Gemini временно перегружен ({last_error}). Пожалуйста, попробуйте отправить запрос еще раз."
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
                        return clean_marketplace_links(raw_text)
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
            model = "gemini-flash-lite-latest"
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
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 8192,
                        "thinkingConfig": {"thinkingBudget": 512}
                    }
                }
                models_to_try = [model]
                for fb in ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-1.5-flash"]:
                    if fb not in models_to_try:
                        models_to_try.append(fb)

                connected = False
                for try_model in models_to_try:
                    try_url = f"https://generativelanguage.googleapis.com/v1beta/models/{try_model}:streamGenerateContent?key={api_key}&alt=sse"
                    for attempt in range(2):
                        logger.info(f"Streaming request to Gemini API (Model: {try_model}, Attempt: {attempt+1}, Proxy: {llm_proxy or 'direct'})...")
                        try:
                            async with session.post(try_url, json=payload, proxy=llm_proxy, timeout=75) as resp:
                                if resp.status == 200:
                                    connected = True
                                    async for line_bytes in resp.content:
                                        line = line_bytes.decode('utf-8', errors='ignore').strip()
                                        if not line or not line.startswith("data:"):
                                            continue
                                        data_str = line[5:].strip()
                                        try:
                                            parsed = json.loads(data_str)
                                            if parsed.get("error"):
                                                logger.warning(f"Mid-stream Gemini error: {parsed['error']}")
                                                yield "<br><br>⚠️ <i>[Ответ временно приостановлен из-за нагрузки на сервер Gemini. Нажмите «Продолжай»]</i>"
                                                return
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
                                elif resp.status in (429, 503, 500):
                                    await asyncio.sleep(1.5)
                                    continue
                                break
                        except Exception as stream_err:
                            logger.warning(f"Stream connect attempt failed: {stream_err}")
                            await asyncio.sleep(1.0)
                    if connected:
                        return

                yield "⚠️ Сервис нейросети временно испытывает пиковую нагрузку. Пожалуйста, повторите запрос через несколько секунд."
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
        'chat_bot.js': 'chat_bot.js',
        'rig_visualizer.js': 'rig_visualizer.js'
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
    app.router.add_get(r'/{filename:(?:style\.css|app\.js|auth\.js|chat_bot\.js|rig_visualizer\.js)}', handle_safe_static)
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
