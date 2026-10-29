import os
import sys
import json
import asyncio
import logging
import html
import socket
import urllib.parse
from typing import Dict, Any, Optional, List
import aiohttp
import dotenv

from db.database import (
    add_expert_component,
    get_expert_components,
    delete_expert_component,
    add_ai_rule,
    get_ai_rules,
    get_prompt_template,
    delete_ai_rule,
    reset_ai_rules,
    reset_prompt_template,
    update_prompt_template,
    get_stats
)

logger = logging.getLogger("skyrex_tg_bot")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()


def _parse_admin_ids(value: str) -> set[int]:
    """Parse Telegram user IDs from the TG_ADMIN_IDS environment variable."""
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if any(not part.isdigit() for part in parts):
        raise ValueError("TG_ADMIN_IDS must contain comma-separated numeric Telegram IDs.")
    return {int(part) for part in parts}


ADMIN_IDS = _parse_admin_ids(os.getenv("TG_ADMIN_IDS", ""))

CATEGORY_ICONS = {
    "gpu": "🎮 Видеокарта",
    "cpu": "⚡️ Процессор",
    "motherboard": "🔌 Материнская плата",
    "ram": "🧠 ОЗУ / Память",
    "ssd": "💾 Накопитель / SSD",
    "psu": "🔋 Блок питания",
    "case": "📦 Корпус",
    "cooler": "❄️ Охлаждение / Кулер",
    "other": "⚙️ Комплектующее",
}


class TelegramAdminBot:
    def __init__(self, token: str = TOKEN, admin_ids: set = ADMIN_IDS):
        self.token = token
        self.admin_ids = admin_ids
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_running = False
        
        # State storage
        self.pending_actions: Dict[int, Dict[str, Any]] = {}
        self.user_drafts: Dict[int, Dict[str, Any]] = {}
        self.pending_prompt_edits: set[int] = set()

    async def start(self):
        """Starts long polling loop."""
        if not self.token:
            raise RuntimeError("TG_BOT_TOKEN must be configured in the environment.")
        if not self.admin_ids:
            raise RuntimeError("TG_ADMIN_IDS must contain at least one Telegram user ID.")

        self.is_running = True
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40))
        logger.info(f"Telegram Admin Bot starting for admins: {self.admin_ids}...")
        
        offset = 0
        while self.is_running:
            try:
                updates = await self.get_updates(offset=offset, timeout=25)
                for update in updates:
                    update_id = update.get("update_id", 0)
                    offset = max(offset, update_id + 1)
                    await self.handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in TG polling loop: {e}")
                await asyncio.sleep(3)
                
        if self.session and not self.session.closed:
            await self.session.close()
        logger.info("Telegram Admin Bot stopped.")

    async def stop(self):
        self.is_running = False

    async def api_request(self, method: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/{method}"
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40))
        async with self.session.post(url, json=data or {}) as resp:
            return await resp.json()

    async def get_updates(self, offset: int, timeout: int = 25) -> List[Dict[str, Any]]:
        res = await self.api_request("getUpdates", {"offset": offset, "timeout": timeout})
        if res.get("ok"):
            return res.get("result", [])
        return []

    async def send_message(self, chat_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        res = await self.api_request("sendMessage", data)
        if not res.get("ok"):
            logger.error(f"Failed to send HTML message ({res.get('description')}): {text[:150]}")
            if "can't parse entities" in str(res.get("description", "")).lower():
                data.pop("parse_mode", None)
                res = await self.api_request("sendMessage", data)
        return res

    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_markup is not None:
            data["reply_markup"] = reply_markup
        return await self.api_request("editMessageText", data)

    async def answer_callback(self, callback_id: str, text: Optional[str] = None) -> Dict[str, Any]:
        data = {"callback_query_id": callback_id}
        if text:
            data["text"] = text
        return await self.api_request("answerCallbackQuery", data)

    async def handle_update(self, update: Dict[str, Any]):
        if "message" in update:
            await self.handle_message(update["message"])
        elif "callback_query" in update:
            await self.handle_callback(update["callback_query"])

    async def handle_message(self, msg: Dict[str, Any]):
        user = msg.get("from", {})
        user_id = user.get("id")
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()

        if not user_id or not chat_id:
            return

        # Security check: Admins only
        if user_id not in self.admin_ids:
            logger.warning(f"Unauthorized access attempt from user_id: {user_id} (@{user.get('username')})")
            await self.send_message(
                chat_id,
                "⛔️ <b>Доступ запрещен.</b>\nЭтот бот предназначен исключительно для администраторов Skyrex Computers."
            )
            return

        if not text:
            await self.send_message(chat_id, "Пожалуйста, отправьте текстовое сообщение или команду.")
            return

        if chat_id in self.pending_prompt_edits:
            if text.lower() == "/cancel":
                self.pending_prompt_edits.remove(chat_id)
                await self.send_message(chat_id, "Изменение системного промпта отменено.")
                return
            if text.startswith("/"):
                await self.send_message(
                    chat_id,
                    "Отправьте новый системный промпт одним сообщением или используйте "
                    "<code>/cancel</code> для отмены.",
                )
                return

            update_prompt_template("assistant_system", text)
            self.pending_prompt_edits.remove(chat_id)
            await self.send_message(
                chat_id,
                "✅ Системный промпт консультанта полностью заменён и сохранён в SQLite.",
            )
            return

        # Commands
        if text.startswith("/"):
            await self.handle_command(chat_id, user_id, text)
            return

        # Natural language processing via Gemini
        await self.process_natural_language(chat_id, user_id, text)

    async def handle_command(self, chat_id: int, user_id: int, text: str):
        cmd = text.split()[0].lower()
        args = text.split()[1:]

        if cmd in ("/start", "/help"):
            welcome = (
                "👋 <b>Панель управления Skyrex Computers</b>\n\n"
                "Я помогаю вести <b>Базу мнений и оценок эксперта</b> и обучать ИИ-консультанта на сайте <b>skyrex.pro</b>.\n\n"
                "<b>💡 Как использовать:</b>\n"
                "• <b>Оценка или мнение о модели (применяется ко ВСЕМ вендорам и новым/б-у товарам):</b>\n"
                "  <i>«RTX 4060 оценка 9 отличная энергоэффективная карта для FullHD»</i>\n"
                "  <i>«MSI Ventus 2X оценка 5 очень шумная и горячая»</i>\n"
                "  <i>«Ryzen 5 7500F оценка 10 топ за свои деньги, лучший проц для игр»</i>\n\n"
                "• <b>Обучить нейросеть правилам диалога:</b>\n"
                "  <i>«Запомни: в сборках до 60к предлагать только Deepcool PK550D или Montech Gamma, китайские БП запрещены»</i>\n\n"
                "<b>📋 Доступные команды:</b>\n"
                "/list — Последние 10 оценок в базе мнений\n"
                "/rules — Свод правил ИИ-консультанта\n"
                "/del_rule &lt;ID&gt; — Удалить конкретное правило\n"
                "/reset_rules — Восстановить все правила по умолчанию\n"
                "/prompt — Базовый системный промпт консультанта\n"
                "/add_prompt — Заменить системный промпт\n"
                "/del_prompt — Сбросить системный промпт к исходному\n"
                "/stats — Общая статистика каталога и базы\n"
                "/del_comp &lt;ID&gt; — Удалить оценку комплектующего"
            )
            await self.send_message(chat_id, welcome)

        elif cmd == "/list":
            comps = get_expert_components(limit=10)
            if not comps:
                await self.send_message(chat_id, "📭 В базе мнений пока пусто. Напишите модель и оценку, чтобы добавить первую!")
                return
            lines = ["📋 <b>База мнений и экспертных оценок Skyrex:</b>\n"]
            for component in comps:
                icon = CATEGORY_ICONS.get(component.get("type", "other"), "⚙️")
                price = f"{component.get('price', 0):,} ₽".replace(",", " ") if component.get('price') else "б/у ориентир не задан"
                lines.append(
                    f"<b>#{component['id']}</b> {icon} <b>{component['componentname']}</b>\n"
                    f"   Оценка: ⭐️ <b>{component.get('mark', 'N/A')}/10</b> | Цена: {price}\n"
                    f"   <i>Мнение: {component.get('comment') or 'без комментария'}</i>\n"
                    f"   <i>Удалить: /del_comp {component['id']}</i>\n"
                )
            await self.send_message(chat_id, "\n".join(lines))

        elif cmd == "/rules":
            if args and args[0].lower() in ("prompt", "full"):
                prompt_text = get_prompt_template("assistant_system")
                prompt_chunks = [
                    prompt_text[index:index + 1500]
                    for index in range(0, len(prompt_text), 1500)
                ]
                await self.send_message(
                    chat_id,
                    "🧠 <b>Базовый системный промпт консультанта</b>\n"
                    "Заменить: /add_prompt | Сбросить: /del_prompt",
                )
                for index, chunk in enumerate(prompt_chunks, start=1):
                    await self.send_message(
                        chat_id,
                        f"<b>Системный промпт, часть {index}/{len(prompt_chunks)}:</b>\n"
                        f"<pre>{html.escape(chunk)}</pre>",
                    )
                return

            rules = get_ai_rules(active_only=True)
            if not rules:
                await self.send_message(
                    chat_id,
                    "🧠 <b>Активные правила обучения ИИ</b>\n\n"
                    "Пока нет дополнительных правил. Напишите правило обычным сообщением, чтобы добавить!\n\n"
                    "<i>Посмотреть базовый системный промпт: /prompt</i>",
                )
                return

            header = f"🧠 <b>Активные правила обучения ИИ на skyrex.pro ({len(rules)} шт.):</b>\n\n"
            current_chunk = header
            chunks = []

            for r in rules:
                rule_id = r["id"]
                title = html.escape(r.get("title") or "Инструкция")
                rule_text = html.escape(r["rule_text"])
                rule_entry = (
                    f"<b>Правило #{rule_id}</b> [{title}]:\n"
                    f"«{rule_text}»\n"
                    f"<i>Удалить: /del_rule {rule_id}</i>\n\n"
                )
                if len(current_chunk) + len(rule_entry) > 3500:
                    chunks.append(current_chunk.strip())
                    current_chunk = rule_entry
                else:
                    current_chunk += rule_entry

            if current_chunk.strip():
                chunks.append(current_chunk.strip())

            for chunk in chunks:
                await self.send_message(chat_id, chunk)

            await self.send_message(
                chat_id,
                "💡 <i>Удалить конкретное правило: /del_rule &lt;ID&gt;\n"
                "Сбросить все правила к исходным: /reset_rules\n"
                "Базовый системный промпт консультанта: /prompt\n"
                "Чтобы добавить новое правило, просто напишите его в чат!</i>",
            )

        elif cmd == "/add_prompt":
            self.pending_prompt_edits.add(chat_id)
            await self.send_message(
                chat_id,
                "Отправьте следующим сообщением новый системный промпт консультанта. "
                "Он полностью заменит текущий. Чтобы отменить, отправьте <code>/cancel</code>.",
            )

        elif cmd == "/del_prompt":
            reset_prompt_template("assistant_system")
            self.pending_prompt_edits.discard(chat_id)
            await self.send_message(
                chat_id,
                "✅ Текущий системный промпт удалён и восстановлен исходный промпт по умолчанию.",
            )

        elif cmd == "/prompt":
            prompt_kind = args[0].lower() if args else "assistant"
            prompt_names = {
                "assistant": ("assistant_system", "системный промпт консультанта"),
                "parser": ("telegram_parser", "промпт Telegram-парсера"),
            }
            if prompt_kind not in prompt_names:
                await self.send_message(
                    chat_id,
                    "⚠️ Использование: <code>/prompt</code> для консультанта или "
                    "<code>/prompt parser</code> для Telegram-парсера.",
                )
                return

            template_name, title = prompt_names[prompt_kind]
            prompt_text = get_prompt_template(template_name)
            chunks = [
                prompt_text[index:index + 600]
                for index in range(0, len(prompt_text), 600)
            ]
            await self.send_message(
                chat_id,
                f"🧠 <b>{title.capitalize()} из SQLite.</b>\n"
                "Каталог и активные правила из <code>/rules</code> добавляются отдельно.\n"
                f"Часть 1/{len(chunks)}:\n<pre>{html.escape(chunks[0])}</pre>",
            )
            for index, chunk in enumerate(chunks[1:], start=2):
                await self.send_message(
                    chat_id,
                    f"🧠 <b>{title.capitalize()}, часть {index}/{len(chunks)}:</b>\n"
                    f"<pre>{html.escape(chunk)}</pre>",
                )

        elif cmd == "/stats":
            stats = get_stats()
            msg = (
                "📊 <b>Статистика Skyrex Computers:</b>\n\n"
                f"• 🌐 <b>Сайт:</b> https://skyrex.pro/\n"
                f"• 🛒 <b>Товаров в каталоге ОнлайнТрейд:</b> {stats.get('total_products', 0):,}\n"
                f"• 📦 <b>Экспертных комплектующих:</b> {stats.get('expert_components_count', 0)}\n"
                f"• 🧠 <b>Правил обучения ИИ:</b> {stats.get('ai_rules_count', 0)}\n"
            )
            await self.send_message(chat_id, msg)

        elif cmd == "/del_comp":
            if not args or not args[0].isdigit():
                await self.send_message(chat_id, "⚠️ Укажите ID комплектующего. Пример: <code>/del_comp 15</code>")
                return
            comp_id = int(args[0])
            if delete_expert_component(comp_id):
                await self.send_message(chat_id, f"✅ Комплектующее #{comp_id} успешно удалено из базы.")
            else:
                await self.send_message(chat_id, f"❌ Комплектующее #{comp_id} не найдено.")

        elif cmd == "/del_rule":
            if not args or not args[0].isdigit():
                await self.send_message(chat_id, "⚠️ Укажите ID правила. Пример: <code>/del_rule 2</code>")
                return
            rule_id = int(args[0])
            if delete_ai_rule(rule_id):
                await self.send_message(chat_id, f"✅ Правило ИИ #{rule_id} успешно удалено. ИИ на сайте больше не будет его использовать.")
            else:
                await self.send_message(chat_id, f"❌ Правило #{rule_id} не найдено.")

        elif cmd == "/reset_rules":
            count = reset_ai_rules()
            await self.send_message(
                chat_id,
                f"✅ Все правила ИИ успешно сброшены к эталонным по умолчанию ({count} правил восстановлено).\n"
                "Список актуальных правил можно просмотреть командой /rules.",
            )

        else:
            await self.send_message(chat_id, "Неизвестная команда. Введите /help для просмотра списка команд.")

    async def call_gemini_parser(self, prompt_text: str) -> Optional[Dict[str, Any]]:
        """Calls Gemini API to extract an AI rule from administrator input."""
        api_key = os.getenv("LLM_API_KEY", "")
        if not api_key:
            logger.error("LLM_API_KEY is missing in environment!")
            return None

        model = os.getenv("LLM_MODEL", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        payload = {
            "systemInstruction": {
                "parts": [{"text": get_prompt_template("telegram_parser")}]
            },
            "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
        }

        # Handle optional proxy fallback
        proxy = os.getenv("LLM_PROXY", "").strip() or None
        if proxy and proxy.lower() in ("none", "direct", "off", "false", "no"):
            proxy = None
        if proxy:
            try:
                parsed_proxy = urllib.parse.urlparse(proxy)
                proxy_host = parsed_proxy.hostname or "127.0.0.1"
                proxy_port = parsed_proxy.port or (443 if parsed_proxy.scheme == "https" else 80)
                with socket.create_connection((proxy_host, proxy_port), timeout=0.3):
                    pass
            except (OSError, ValueError):
                logger.warning("Configured LLM proxy is unreachable. Falling back to a direct connection.")
                proxy = None

        try:
            async with self.session.post(url, json=payload, proxy=proxy, timeout=25) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Gemini parser returned status {resp.status}: {text}")
                    return None
                data = await resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw_text)
        except Exception as e:
            logger.error(f"Error calling Gemini parser: {e}")
            return None

    async def process_natural_language(self, chat_id: int, user_id: int, text: str):
        input_text = text
        if chat_id in self.user_drafts:
            draft = self.user_drafts[chat_id]
            input_text = (
                f"Исходный компонент: {draft.get('name', '')}. "
                f"Дополнительные детали от администратора: {text}"
            )
            del self.user_drafts[chat_id]

        parsed = await self.call_gemini_parser(input_text)
        if not parsed:
            await self.send_message(chat_id, "⚠️ Не удалось распознать сообщение. Пожалуйста, попробуйте сформулировать иначе.")
            return

        intent = parsed.get("intent")

        if intent == "clarify_needed":
            component = parsed.get("component") or {}
            self.user_drafts[chat_id] = component
            question = parsed.get("clarify_question") or (
                f"Укажите примерную цену для <b>{component.get('name', 'этого компонента')}</b>."
            )
            await self.send_message(chat_id, f"🤔 {question}")
            return

        elif intent == "add_component":
            component = parsed.get("component")
            if not component or not component.get("name"):
                await self.send_message(chat_id, "⚠️ Не удалось определить название комплектующего. Уточните его.")
                return

            self.pending_actions[chat_id] = {
                "type": "comp",
                "data": component,
                "user_id": user_id,
            }

            category = CATEGORY_ICONS.get(component.get("category", "other"), "⚙️ Комплектующее")
            price = f"{component.get('price', 0):,} ₽".replace(",", " ")
            min_price = (
                f" (мин. {component.get('minprice'):,} ₽)"
                if component.get("minprice")
                else ""
            )
            comment = component.get("comment") or "Нет комментария"
            card = (
                "⭐️ <b>Подтвердите добавление в Базу мнений и оценок:</b>\n\n"
                f"• <b>Тип:</b> {category}\n"
                f"• <b>Модель:</b> <b>{component['name']}</b>\n"
                f"• <b>Оценка эксперта:</b> ⭐️ <b>{component.get('mark') or 8}/10</b>\n"
            )
            if component.get('price'):
                card += f"• <b>Ориентир цены:</b> {price}{min_price}\n"
            card += f"• <b>Вердикт/мнение:</b> <i>{comment}</i>\n"
            if component.get("analogue"):
                card += f"• <b>Аналоги:</b> {component['analogue']}\n"
            card += (
                "\n💡 <i>Эта оценка и вердикт автоматически распространяются на все исполнения "
                "(Palit, MSI, Gigabyte и др., как новые в магазинах, так и б/у) на сайте skyrex.pro!</i>\n\n"
                "<i>Сохранить в базу мнений?</i>"
            )
            keyboard = {
                "inline_keyboard": [[
                    {"text": "✅ Сохранить", "callback_data": "confirm_save"},
                    {"text": "❌ Отмена", "callback_data": "cancel_action"},
                ]]
            }
            await self.send_message(chat_id, card, reply_markup=keyboard)
            return

        if intent == "add_rule":
            rule = parsed.get("rule")
            if not rule or not rule.get("rule_text"):
                await self.send_message(chat_id, "⚠️ Не удалось сформулировать правило. Пожалуйста, напишите чуть подробнее.")
                return

            self.pending_actions[chat_id] = {
                "type": "rule",
                "data": rule,
                "user_id": user_id
            }

            title = rule.get("title") or "Правило эксперта"
            card = (
                "🧠 <b>Подтвердите добавление правила для ИИ:</b>\n\n"
                f"• <b>Тема:</b> <b>{title}</b>\n"
                f"• <b>Инструкция для бота:</b>\n<i>«{rule['rule_text']}»</i>\n\n"
                "<i>Нейросеть на сайте skyrex.pro сразу начнет соблюдать это правило при подборе сборок и ответах. Сохранить?</i>"
            )
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Да, обучить нейросеть", "callback_data": "confirm_save"},
                        {"text": "❌ Отмена", "callback_data": "cancel_action"}
                    ]
                ]
            }
            await self.send_message(chat_id, card, reply_markup=keyboard)

        else:
            await self.send_message(
                chat_id,
                "🤔 Не совсем понял. Напишите комплектующее с примерной ценой или правило для ИИ. "
                "Введите /help для примеров."
            )

    async def handle_callback(self, cb: Dict[str, Any]):
        cb_id = cb.get("id")
        data = cb.get("data")
        msg = cb.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        message_id = msg.get("message_id")
        user = cb.get("from", {})
        user_id = user.get("id")

        if not chat_id or not user_id:
            return

        if user_id not in self.admin_ids:
            await self.answer_callback(cb_id, "Доступ запрещен.")
            return

        if data == "cancel_action":
            if chat_id in self.pending_actions:
                del self.pending_actions[chat_id]
            await self.answer_callback(cb_id, "Действие отменено.")
            await self.edit_message(chat_id, message_id, "❌ <i>Действие отменено.</i>")
            return

        if data == "confirm_save":
            action = self.pending_actions.get(chat_id)
            if not action:
                await self.answer_callback(cb_id, "Данные устарели или уже сохранены.")
                await self.edit_message(chat_id, message_id, "⚠️ <i>Действие уже было выполнено или отменено.</i>")
                return

            action_type = action.get("type")
            item_data = action.get("data", {})

            if action_type == "comp":
                component = {
                    "type": item_data.get("category", "other"),
                    "componentname": item_data.get("name", "Без названия"),
                    "mark": item_data.get("mark", 8),
                    "price": int(item_data.get("price", 0)),
                    "minprice": int(item_data.get("minprice")) if item_data.get("minprice") else None,
                    "comment": item_data.get("comment", ""),
                    "analogue": item_data.get("analogue", ""),
                    "created_by": str(user_id),
                }
                new_id = add_expert_component(component)
                del self.pending_actions[chat_id]

                await self.answer_callback(cb_id, "Успешно сохранено!")
                price_str = f" ({component['price']:,} ₽)" if component['price'] else ""
                await self.edit_message(
                    chat_id,
                    message_id,
                    f"✅ <b>Экспертная оценка сохранена в базу мнений!</b> (ID: <code>#{new_id}</code>)\n\n"
                    f"• <b>{component['componentname']}</b> — ⭐️ <b>{component['mark']}/10</b>{price_str}\n"
                    f"• <i>Вердикт:</i> <i>{component['comment'] or 'без комментария'}</i>\n\n"
                    "💡 <i>Оценка и вердикт автоматически действуют на все вендоры (Palit, MSI и т.д.) "
                    "и новые/б-у товары этой модели на сайте skyrex.pro!</i>",
                )

            elif action_type == "rule":
                rule_text = item_data.get("rule_text", "")
                title = item_data.get("title", "")
                new_id = add_ai_rule(rule_text, title=title, created_by=str(user_id))
                del self.pending_actions[chat_id]

                await self.answer_callback(cb_id, "Правило сохранено!")
                await self.edit_message(
                    chat_id,
                    message_id,
                    f"🧠 <b>Нейросеть успешно обучена!</b> (Правило <code>#{new_id}</code>)\n\n"
                    f"• <b>Тема:</b> {title}\n"
                    f"• <b>Инструкция:</b> <i>«{rule_text}»</i>\n\n"
                    f"ИИ-консультант на <b>https://skyrex.pro/</b> уже соблюдает это правило."
                )

# Standalone execution for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    bot = TelegramAdminBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
