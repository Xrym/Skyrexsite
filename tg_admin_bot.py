import os
import sys
import json
import asyncio
import logging
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
    delete_ai_rule,
    get_stats
)

logger = logging.getLogger("skyrex_tg_bot")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

TOKEN = os.getenv("TG_BOT_TOKEN", "***REMOVED_TELEGRAM_BOT_TOKEN***").strip()
admin_env = os.getenv("TG_ADMIN_IDS", "1755491562,7775798957")
ADMIN_IDS = set()
for part in admin_env.split(","):
    part = part.strip()
    if part.isdigit():
        ADMIN_IDS.add(int(part))

CATEGORY_ICONS = {
    "gpu": "🎮 Видеокарта",
    "cpu": "⚡️ Процессор",
    "motherboard": "🔌 Материнская плата",
    "ram": "🧠 ОЗУ / Память",
    "ssd": "💾 Накопитель / SSD",
    "psu": "🔋 Блок питания",
    "case": "📦 Корпус",
    "cooler": "❄️ Охлаждение / Кулер",
    "other": "⚙️ Комплектующее"
}

PARSER_PROMPT = """Ты — интеллектуальный ассистент-парсер для магазина игровых ПК Skyrex Computers.
Администратор магазина присылает сообщение о компьютерном железе (Б/У на вторичке/Авито) или обучающее правило для ИИ.

Твоя задача — извлечь данные и вернуть СТРОГО один валидный JSON-объект без форматирования markdown (без ```json):
{
  "intent": "add_component" | "add_rule" | "clarify_needed",
  "component": {
    "category": "gpu" | "cpu" | "motherboard" | "ram" | "ssd" | "psu" | "case" | "cooler" | "other",
    "name": "Точное понятное название комплектующего",
    "price": 30000,
    "minprice": null,
    "mark": 8,
    "comment": "Понятное описание и вердикт эксперта",
    "analogue": "Аналоги (если упомянуты) или ''"
  },
  "rule": {
    "title": "Краткая тема правила",
    "rule_text": "Четкая инструкция для ИИ-консультанта"
  },
  "clarify_question": "Вежливый вопрос к админу, если не хватает критических данных (например, цены или оценки)"
}

ПРАВИЛА КЛАССИФИКАЦИИ:
1. Если админ упоминает конкретное железо (видюха, карта, проц, кулер, плата, память, бп, корпус):
   - Если указана хотя бы примерная цена: intent = "add_component". Если оценка не указана, поставь разумную по умолчанию (7 или 8).
   - Если цены вообще нет и это непонятно: intent = "clarify_needed", заполни clarify_question.
2. Если админ говорит, как отвечать, что советовать, что запрещено, правила сборок или поведения: intent = "add_rule".
3. Автоматически нормализуй названия (например "3070ти" -> "NVIDIA GeForce RTX 3070 Ti", "5600" -> "AMD Ryzen 5 5600", "ak620" -> "DeepCool AK620").
"""

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

    async def start(self):
        """Starts long polling loop."""
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
        return await self.api_request("sendMessage", data)

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
                "Я помогаю наполнять базу Б/У комплектующих и обучать ИИ-консультанта на сайте <b>skyrex.pro</b>.\n\n"
                "<b>💡 Как использовать:</b>\n"
                "• <b>Добавить Б/У компонент:</b>\n"
                "  Просто напишите текстом своими словами, например:\n"
                "  <i>«видюха 3070ti на авито щас где-то 30к, норм вариант но горячая память, ставь 8»</i>\n\n"
                "• <b>Обучить нейросеть:</b>\n"
                "  Напишите правило общения или подбора, например:\n"
                "  <i>«Запомни: в сборках до 60к предлагать только Deepcool PK550D или Montech Gamma, китайские БП запрещены»</i>\n\n"
                "<b>📋 Доступные команды:</b>\n"
                "/list — Последние 10 Б/У комплектующих в базе\n"
                "/rules — Список активных правил для ИИ\n"
                "/stats — Общая статистика каталога и базы\n"
                "/del_comp &lt;ID&gt; — Удалить комплектующее\n"
                "/del_rule &lt;ID&gt; — Удалить правило ИИ"
            )
            await self.send_message(chat_id, welcome)

        elif cmd == "/list":
            comps = get_expert_components(limit=10)
            if not comps:
                await self.send_message(chat_id, "📭 В базе пока нет Б/У комплектующих. Напишите текст, чтобы добавить первый!")
                return
            lines = ["📋 <b>Последние Б/У комплектующие в базе:</b>\n"]
            for c in comps:
                icon_tag = CATEGORY_ICONS.get(c.get("type", "other"), "⚙️")
                price_str = f"{c.get('price', 0):,} ₽".replace(",", " ")
                lines.append(
                    f"<b>#{c['id']}</b> {icon_tag} <b>{c['componentname']}</b>\n"
                    f"   Цена: {price_str} | Оценка: ⭐️ {c.get('mark', 'N/A')}/10\n"
                    f"   <i>Удалить: /del_comp {c['id']}</i>\n"
                )
            await self.send_message(chat_id, "\n".join(lines))

        elif cmd == "/rules":
            rules = get_ai_rules(active_only=True)
            if not rules:
                await self.send_message(chat_id, "🧠 Пока нет добавленных правил обучения ИИ. Напишите правило (например, <i>«Запомни: ...»</i>), чтобы добавить.")
                return
            lines = ["🧠 <b>Активные правила обучения ИИ на skyrex.pro:</b>\n"]
            for r in rules:
                lines.append(
                    f"<b>Правило #{r['id']}</b> [{r.get('title') or 'Инструкция'}]:\n"
                    f"«{r['rule_text']}»\n"
                    f"<i>Удалить: /del_rule {r['id']}</i>\n"
                )
            await self.send_message(chat_id, "\n".join(lines))

        elif cmd == "/stats":
            stats = get_stats()
            msg = (
                "📊 <b>Статистика Skyrex Computers:</b>\n\n"
                f"• 🌐 <b>Сайт:</b> https://skyrex.pro/\n"
                f"• 🛒 <b>Товаров в каталоге ОнлайнТрейд:</b> {stats.get('total_products', 0):,}\n"
                f"• 📦 <b>Экспертных Б/У комплектующих:</b> {stats.get('expert_components_count', 0)}\n"
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

        else:
            await self.send_message(chat_id, "Неизвестная команда. Введите /help для просмотра списка команд.")

    async def call_gemini_parser(self, prompt_text: str) -> Optional[Dict[str, Any]]:
        """Calls Gemini API with JSON output mode to extract structured component or rule."""
        api_key = os.getenv("LLM_API_KEY", "")
        if not api_key:
            logger.error("LLM_API_KEY is missing in environment!")
            return None

        model = os.getenv("LLM_MODEL", "gemini-3.5-flash-lite")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        payload = {
            "systemInstruction": {"parts": [{"text": PARSER_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
        }

        # Handle optional proxy fallback
        proxy = os.getenv("LLM_PROXY", "").strip() or None
        if proxy and proxy.lower() in ("none", "direct", "off", "false"):
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
        # If user had a pending draft waiting for clarification, combine them
        input_text = text
        if chat_id in self.user_drafts:
            draft = self.user_drafts[chat_id]
            input_text = f"Исходный компонент: {draft.get('name', '')}. Дополнительные детали от админа: {text}"
            del self.user_drafts[chat_id]

        parsed = await self.call_gemini_parser(input_text)
        if not parsed:
            await self.send_message(chat_id, "⚠️ Не удалось распознать сообщение. Пожалуйста, попробуйте сформулировать иначе.")
            return

        intent = parsed.get("intent")

        if intent == "clarify_needed":
            comp = parsed.get("component") or {}
            self.user_drafts[chat_id] = comp
            question = parsed.get("clarify_question") or f"Укажите ориентировочную цену для <b>{comp.get('name', 'этого компонента')}</b> и оценку (от 1 до 10)."
            await self.send_message(chat_id, f"🤔 {question}")
            return

        elif intent == "add_component":
            comp = parsed.get("component")
            if not comp or not comp.get("name"):
                await self.send_message(chat_id, "⚠️ Не удалось определить название комплектующего. Пожалуйста, уточните.")
                return

            self.pending_actions[chat_id] = {
                "type": "comp",
                "data": comp,
                "user_id": user_id
            }

            cat_icon = CATEGORY_ICONS.get(comp.get("category", "other"), "⚙️ Комплектующее")
            price_str = f"{comp.get('price', 0):,} ₽".replace(",", " ")
            min_str = f" (мин. {comp.get('minprice'):,} ₽)".replace(",", " ") if comp.get("minprice") else ""
            mark = comp.get("mark") or 8
            comment = comp.get("comment") or "Нет комментария"
            analogue = comp.get("analogue")

            card = (
                "📦 <b>Подтвердите добавление комплектующего:</b>\n\n"
                f"• <b>Тип:</b> {cat_icon}\n"
                f"• <b>Название:</b> <b>{comp['name']}</b>\n"
                f"• <b>Ориентир цены:</b> {price_str}{min_str}\n"
                f"• <b>Оценка эксперта:</b> ⭐️ {mark}/10\n"
                f"• <b>Вердикт:</b> <i>{comment}</i>\n"
            )
            if analogue:
                card += f"• <b>Аналоги:</b> {analogue}\n"
            card += "\n<i>Сохранить на сайт skyrex.pro и в базу ИИ-консультанта?</i>"

            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Да, сохранить на сайт", "callback_data": "confirm_save"},
                        {"text": "❌ Отмена", "callback_data": "cancel_action"}
                    ]
                ]
            }
            await self.send_message(chat_id, card, reply_markup=keyboard)

        elif intent == "add_rule":
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
                "🤔 Не совсем понял. Вы хотите добавить комплектующее или правило для ИИ? "
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
                comp_to_save = {
                    "type": item_data.get("category", "other"),
                    "componentname": item_data.get("name", "Без названия"),
                    "mark": item_data.get("mark", 8),
                    "price": int(item_data.get("price", 0)),
                    "minprice": int(item_data.get("minprice")) if item_data.get("minprice") else None,
                    "comment": item_data.get("comment", ""),
                    "analogue": item_data.get("analogue", ""),
                    "created_by": str(user_id)
                }
                new_id = add_expert_component(comp_to_save)
                del self.pending_actions[chat_id]

                await self.answer_callback(cb_id, "Успешно сохранено!")
                await self.edit_message(
                    chat_id,
                    message_id,
                    f"✅ <b>Комплектующее успешно добавлено в базу!</b> (ID: <code>#{new_id}</code>)\n\n"
                    f"• <b>{comp_to_save['componentname']}</b> ({comp_to_save['price']:,} ₽)\n"
                    f"• Доступно на сайте <b>https://skyrex.pro/</b>\n"
                    f"• ИИ-консультант уже знает о нем и будет предлагать клиентам."
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
