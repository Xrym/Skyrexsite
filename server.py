import os
import re
import json
import logging
import secrets
import asyncio
from typing import Optional, Dict, Any, List
import aiohttp
from aiohttp import web
import dotenv

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
from db.database import seed_from_bot_db, get_stats, get_connection
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
    
    # 1. Search for specific items mentioned in user message (e.g. 'RTX 4070', 'Kingston')
    if user_message:
        words = [w for w in re.sub(r'[^\w\s]', ' ', user_message).split() if len(w) >= 3 and not w.isdigit()]
        for w in words[:5]:
            found = search_price(query=w, limit=4)
            for item in found:
                if not any(x['id'] == item['id'] for x in specific_results):
                    specific_results.append(item)
                    
    general_build_keywords = ['пк', 'сборк', 'собери', 'компьютер', 'бюджет', 'детал', 'конфигурац', 'купить', 'ценами', 'ситилинк', 'цена', 'сколько']
    is_build_request = any(k in user_message.lower() for k in general_build_keywords)
    budget = extract_budget(user_message)
    
    cat_items = []
    if is_build_request or budget or len(specific_results) < 5:
        with get_connection() as conn:
            # Determine target allocations if budget is specified
            max_gpu_price = int(budget * 0.55) if budget else 9999999
            max_cpu_price = int(budget * 0.28) if budget else 9999999
            max_mb_price = int(budget * 0.18) if budget else 9999999
            max_ram_price = int(budget * 0.15) if budget else 9999999

            # A. Select Candidate GPUs fitting budget (ordered by price DESC for max performance)
            gpu_rows = conn.execute(
                "SELECT * FROM products WHERE category = 'gpu' AND price <= ? ORDER BY price DESC LIMIT 5",
                (max_gpu_price,)
            ).fetchall()
            if not gpu_rows:
                gpu_rows = conn.execute("SELECT * FROM products WHERE category = 'gpu' ORDER BY price ASC LIMIT 5").fetchall()
            for r in gpu_rows:
                cat_items.append(dict(r))

            # B. Select Candidate CPUs fitting budget (exclude workstation Threadripper > 150k unless requested)
            cpu_filter_threadripper = " AND name NOT LIKE '%Threadripper%' " if (not budget or budget < 1000000) else ""
            cpu_rows = conn.execute(
                f"SELECT * FROM products WHERE category = 'cpu' AND price <= ? {cpu_filter_threadripper} ORDER BY price DESC LIMIT 6",
                (max_cpu_price,)
            ).fetchall()
            if not cpu_rows:
                cpu_rows = conn.execute("SELECT * FROM products WHERE category = 'cpu' ORDER BY price ASC LIMIT 5").fetchall()
            
            selected_cpus = [dict(r) for r in cpu_rows]
            cat_items.extend(selected_cpus)

            # C. Detect Sockets of selected candidate CPUs to guarantee 100% MOTHERBOARD COMPATIBILITY
            candidate_sockets = set()
            for c in selected_cpus:
                specs = detect_hardware_specs(c)
                if specs["socket"]:
                    candidate_sockets.add(specs["socket"])

            # D. Select Motherboards matching the candidate sockets
            all_mbs = conn.execute(
                "SELECT * FROM products WHERE category = 'motherboard' AND price <= ? ORDER BY price DESC",
                (max_mb_price,)
            ).fetchall()
            if not all_mbs:
                all_mbs = conn.execute("SELECT * FROM products WHERE category = 'motherboard' ORDER BY price DESC").fetchall()

            compatible_mbs = []
            for mb in all_mbs:
                mb_dict = dict(mb)
                specs = detect_hardware_specs(mb_dict)
                if not candidate_sockets or specs["socket"] in candidate_sockets:
                    mb_dict["detected_socket"] = specs["socket"]
                    mb_dict["detected_ram"] = specs["ram_type"]
                    compatible_mbs.append(mb_dict)
                if len(compatible_mbs) >= 8:
                    break
            cat_items.extend(compatible_mbs)

            # E. Detect RAM Types required by selected compatible motherboards (e.g. DDR5 for AM5/LGA 1851)
            required_ram_types = set(mb["detected_ram"] for mb in compatible_mbs if mb.get("detected_ram"))
            all_rams = conn.execute(
                "SELECT * FROM products WHERE category = 'ram' AND price <= ? ORDER BY price DESC",
                (max_ram_price,)
            ).fetchall()
            if not all_rams:
                all_rams = conn.execute("SELECT * FROM products WHERE category = 'ram' ORDER BY price DESC").fetchall()

            compatible_rams = []
            for r in all_rams:
                r_dict = dict(r)
                specs = detect_hardware_specs(r_dict)
                if not required_ram_types or specs["ram_type"] in required_ram_types or not specs["ram_type"]:
                    r_dict["detected_ram"] = specs["ram_type"]
                    compatible_rams.append(r_dict)
                if len(compatible_rams) >= 6:
                    break
            cat_items.extend(compatible_rams)

            # F. Select PSUs (if top GPUs are selected, prioritize high-wattage 750W-1000W+ units)
            psu_rows = conn.execute("SELECT * FROM products WHERE category = 'psu' ORDER BY price DESC LIMIT 5").fetchall()
            cat_items.extend([dict(r) for r in psu_rows])

            # G. Select SSDs
            ssd_rows = conn.execute("SELECT * FROM products WHERE category = 'ssd' ORDER BY price DESC LIMIT 5").fetchall()
            cat_items.extend([dict(r) for r in ssd_rows])

            # H. Select Coolers
            cooler_rows = conn.execute("SELECT * FROM products WHERE category = 'cooler' ORDER BY price DESC LIMIT 5").fetchall()
            cat_items.extend([dict(r) for r in cooler_rows])

            # I. Select Cases
            case_rows = conn.execute("SELECT * FROM products WHERE category = 'case' ORDER BY price DESC LIMIT 5").fetchall()
            cat_items.extend([dict(r) for r in case_rows])

    all_products = specific_results + [p for p in cat_items if not any(x['id'] == p['id'] for x in specific_results)]
    
    if all_products:
        budget_header = f" ПОД БЮДЖЕТ {budget:,} РУБ" if budget else ""
        context_parts.append(f"=== АКТУАЛЬНЫЕ ЦЕНЫ И НАЛИЧИЕ ИЗ ОНЛАЙНТРЕЙД (РЕАЛЬНЫЙ КАТАЛОГ{budget_header}) ===")
        for p in all_products[:45]:
            specs = detect_hardware_specs(p)
            spec_tags = []
            if specs["socket"]:
                spec_tags.append(f"Сокет: {specs['socket']}")
            if specs["ram_type"]:
                spec_tags.append(f"Память: {specs['ram_type']}")
            if specs["psu_watts"]:
                spec_tags.append(f"Мощность: {specs['psu_watts']}W")
            tag_str = f" [{ ' | '.join(spec_tags) }]" if spec_tags else ""

            price_str = f"{p['price']:,} руб".replace(",", " ")
            old_str = f" (старая цена: {p['old_price']:,} руб)".replace(",", " ") if p.get('old_price') else ""
            context_parts.append(f"- [{p.get('shop', 'ОнлайнТрейд')}] [{p.get('category', '').upper()}] {p['name']}. Цена: {price_str}{old_str}{tag_str}. Ссылка: {p['url']}")

    return "\n".join(context_parts)

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

    catalog_text = "=== ОФИЦИАЛЬНЫЙ КАТАЛОГ МАГАЗИНА SKYREX (Б/У И БАЗОВЫЕ ПОЗИЦИИ) ===\n\n"
    catalog_text += "КОМПЛЕКТУЮЩИЕ (В ОСНОВНОМ ВТОРИЧНЫЙ РЫНОК / БУ):\n"
    catalog_text += (
        "Для одинаковой категории и модели используй только одну, самую свежую "
        "запись каталога: новая запись эксперта заменяет прежнюю цену и описание. "
        "Не используй устаревшие значения из истории диалога или аналогов.\n"
    )
    for component in components:
        catalog_text += (
            f"- {component.get('componentname', 'Без названия')} "
            f"({component.get('type', 'other').upper()}). "
            f"Цена: {component.get('price', 'N/A')} руб. "
        )
        if component.get("minprice"):
            catalog_text += f"(Минимальная цена: {component['minprice']} руб). "
        catalog_text += f"Оценка экспертов: {component.get('mark', 'N/A')}/10. "
        comment = component.get("comment", "").replace("\n", " ")
        if comment:
            catalog_text += f"Комментарий: {comment} "
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

    admin_rules_text = ""
    if ai_rules:
        admin_rules_text = (
            "\n\n=== ПРАВИЛА АДМИНИСТРАТОРА ИЗ TELEGRAM (ПРИОРИТЕТ ВЫШЕ БАЗОВОГО ПРОМПТА) ===\n"
            "Это актуальные инструкции администратора. Если инструкция ниже противоречит базовому "
            "промпту или данным каталога, следуй инструкции администратора. Если инструкции "
            "администратора противоречат друг другу, более поздняя (с большим номером) имеет приоритет.\n"
        )
        for i, r in enumerate(ai_rules, 1):
            admin_rules_text += (
                f"{i}. [{r.get('title') or 'Инструкция'}]: {r.get('rule_text')}\n"
            )

    return (
        f"{base_prompt}\n\n"
        f"{catalog_text}\n"
        f"{dynamic_context}"
        f"{admin_rules_text}"
    )


# 3. Call LLM provider with retry & timeout protection
async def call_llm(message, history):
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
            model = "gemini-2.5-flash"
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

    # Dynamic context for the message
    dynamic_context = get_parsed_catalog_context(message)
    system_instruction = build_system_instruction(dynamic_context)

    # Proxy detection for LLM (supports Happ, v2ray, Clash, system proxy, or direct)
    llm_proxy = os.getenv("LLM_PROXY", "").strip() or None
    if llm_proxy and llm_proxy.lower() in ("none", "direct", "false", "off", "no"):
        llm_proxy = None

    import socket
    from urllib.parse import urlparse

    if llm_proxy:
        # Verify configured proxy is actually reachable (avoids failure when transferring .env to VPS)
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
            # Auto-detect local proxy clients on desktop (Happ/v2ray on 10809, Clash on 7890)
            for test_port in (10809, 7890):
                try:
                    with socket.create_connection(("127.0.0.1", test_port), timeout=0.2):
                        llm_proxy = f"http://127.0.0.1:{test_port}"
                        break
                except Exception:
                    pass

    # Convert frontend history to LLM format
    # Frontend history format: [{"sender": "user"/"bot", "text": "..."}]
    async with aiohttp.ClientSession(trust_env=True) as session:
        try:
            if provider == "gemini":
                # Gemini REST Payload
                contents = []
                for msg in history:
                    role = "user" if msg.get("sender") == "user" else "model"
                    contents.append({
                        "role": role,
                        "parts": [{"text": msg.get("text", "")}]
                    })
                # Add current message
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
                        "maxOutputTokens": 2048
                    }
                }
                
                logger.info(f"Sending request to Gemini API (Model: {model}, Proxy: {llm_proxy or 'direct'})...")
                async with session.post(url, json=payload, proxy=llm_proxy, timeout=35) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"Gemini API returned status {resp.status}: {err_text}")
                        return f"⚠️ Ошибка Gemini API ({resp.status}). Пожалуйста, проверьте API-ключ в настройках."
                    
                    result = await resp.json()
                    # Parse response
                    try:
                        return result["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError) as e:
                        logger.error(f"Failed to parse Gemini response: {e}, structure: {result}")
                        return "⚠️ Не удалось распознать ответ от нейросети. Попробуйте еще раз."
            else:
                # OpenAI-compatible REST Payload
                messages = [{"role": "system", "content": system_instruction}]
                for msg in history:
                    role = "user" if msg.get("sender") == "user" else "assistant"
                    messages.append({"role": role, "content": msg.get("text", "")})
                # Add current message
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
                
                # OpenRouter requires special headers to show app name in dashboard
                if provider == "openrouter":
                    headers["HTTP-Referer"] = "https://skyrex.ai"
                    headers["X-Title"] = "Skyrex Computers AI"
                
                logger.info(f"Sending request to OpenAI-compatible {provider} API (Model: {model}, Proxy: {llm_proxy or 'direct'})...")
                async with session.post(url, json=payload, headers=headers, proxy=llm_proxy, timeout=35) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"{provider.upper()} API returned status {resp.status}: {err_text}")
                        return f"⚠️ Ошибка {provider.upper()} API ({resp.status}). Убедитесь, что лимиты и ключ в порядке."
                    
                    result = await resp.json()
                    try:
                        return result["choices"][0]["message"]["content"]
                    except (KeyError, IndexError) as e:
                        logger.error(f"Failed to parse OpenAI response: {e}, structure: {result}")
                        return "⚠️ Не удалось извлечь ответ из нейросети."
                        
        except Exception as e:
            logger.error(f"Connection error to {provider}: {e}")
            return f"⚠️ Не удалось подключиться к серверу нейросети ({type(e).__name__}). Проверьте соединение с интернетом."

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
        # Check authorization token (optional during free beta)
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "").strip() if "Bearer " in auth_header else ""
        current_user = get_user_by_token(token) if token else None

        data = await request.json()
        message = data.get("message", "").strip()
        history = data.get("history", [])
        
        if not message:
            return web.json_response({"response": "Сообщение не может быть пустым."})
            
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
