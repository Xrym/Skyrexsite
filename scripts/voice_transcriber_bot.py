# -*- coding: utf-8 -*-
"""
Skyrex Computers - Telegram Voice Transcriber Bot
Скрипт транскрибации голосовых сообщений (включая пересланные от заказчиков) в текст.
Использует те же токены, настройки и список администраторов из .env:
- TG_BOT_TOKEN
- TG_ADMIN_IDS
- LLM_API_KEY (Google Gemini Multimodal API)
- LLM_MODEL (по умолчанию gemini-flash-lite-latest / gemini-flash-latest)

Запуск:
    python scripts/voice_transcriber_bot.py
"""

import os
import sys
import json
import base64
import html
import asyncio
import logging
import datetime
from typing import Dict, Any, Optional, List, Set
import aiohttp
import dotenv

# Настройка UTF-8 для консоли Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("voice_transcriber")

# Загрузка переменных окружения
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv.load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

TOKEN = os.getenv("TG_BOT_TOKEN", "").strip()


def parse_admin_ids(value: str) -> Set[int]:
    """Извлекает ID администраторов из переменной TG_ADMIN_IDS."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    admin_set = set()
    for p in parts:
        if p.isdigit():
            admin_set.add(int(p))
    return admin_set


ADMIN_IDS = parse_admin_ids(os.getenv("TG_ADMIN_IDS", ""))
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-flash-lite-latest").strip()


class VoiceTranscriberBot:
    """Бот для приема и расшифровки голосовых сообщений от клиентов."""

    def __init__(self, token: str = TOKEN, admin_ids: Set[int] = ADMIN_IDS):
        self.token = token
        self.admin_ids = admin_ids
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session: Optional[aiohttp.ClientSession] = None
        self.is_running = False

    async def api_request(self, method: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Выполняет запрос к Telegram Bot API."""
        url = f"{self.base_url}/{method}"
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))
        async with self.session.post(url, json=data or {}) as resp:
            return await resp.json()

    async def send_message(self, chat_id: int, text: str, reply_to_message_id: Optional[int] = None) -> Dict[str, Any]:
        """Отправляет текстовое сообщение в Telegram."""
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        if reply_to_message_id:
            data["reply_to_message_id"] = reply_to_message_id
        res = await self.api_request("sendMessage", data)
        if not res.get("ok") and "can't parse entities" in str(res.get("description", "")).lower():
            data.pop("parse_mode", None)
            res = await self.api_request("sendMessage", data)
        return res

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> Dict[str, Any]:
        """Редактирует существующее сообщение."""
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        res = await self.api_request("editMessageText", data)
        if not res.get("ok") and "can't parse entities" in str(res.get("description", "")).lower():
            data.pop("parse_mode", None)
            res = await self.api_request("editMessageText", data)
        return res

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        """Удаляет сообщение (например, временный статус загрузки)."""
        res = await self.api_request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        return bool(res.get("ok"))

    async def send_chat_action(self, chat_id: int, action: str = "typing"):
        """Показывает статус действия в чате (typing / upload_document / record_voice)."""
        await self.api_request("sendChatAction", {"chat_id": chat_id, "action": action})

    async def download_telegram_file(self, file_id: str) -> Optional[bytes]:
        """Получает путь к файлу через Telegram Bot API и скачивает его содержимое."""
        file_res = await self.api_request("getFile", {"file_id": file_id})
        if not file_res.get("ok"):
            logger.error(f"Telegram getFile error: {file_res.get('description')}")
            return None

        file_path = file_res["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"

        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))

        async with self.session.get(download_url) as resp:
            if resp.status == 200:
                return await resp.read()
            logger.error(f"Failed to download audio file (HTTP {resp.status})")
            return None

    async def transcribe_with_gemini(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> Optional[str]:
        """Отправляет аудио в Google Gemini Multimodal API для точной расшифровки речи."""
        if not LLM_API_KEY:
            logger.error("LLM_API_KEY is not configured in .env!")
            return None

        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

        prompt = (
            "Ты — высокоточный профессиональный стенографист сервиса подбора ПК Skyrex Computers.\n"
            "Твоя задача — максимально точно, полно и грамотно расшифровать эту аудиозапись "
            "(голосовое сообщение от клиента/заказчика) в текст на русском языке.\n\n"
            "Критически важные правила:\n"
            "1. Сохраняй абсолютно все компьютерные термины, бренды, модели видеокарт, процессоров, памяти "
            "(RTX 4060, Ryzen 5 7500F, DDR5, LGA1700, БП и т.д.), цифры бюджета, цены и требования клиента без искажений.\n"
            "2. Расставь правильные знаки препинания, заглавные буквы и разбей текст на логические абзацы для удобного чтения.\n"
            "3. Если клиент запинается или использует слова-паразиты ('э-э', 'ну вот', 'как бы'), аккуратно сглаживай их, сохраняя точный смысл речи.\n"
            "4. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО добавлять что-либо от себя (никаких приветствий, ответов на вопросы клиента, советов по сборке, пояснений или оценок).\n"
            "5. Выведи ТОЛЬКО чистый расшифрованный текст."
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": mime_type,
                                "data": b64_audio
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        # Список моделей с авто-переключением (fallback)
        models_to_try = [LLM_MODEL, "gemini-flash-latest", "gemini-2.5-flash-lite"]
        seen = set()
        unique_models = [m for m in models_to_try if m and not (m in seen or seen.add(m))]

        for m in unique_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={LLM_API_KEY}"
            try:
                async with self.session.post(url, json=payload, timeout=35) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
                    else:
                        err_text = await resp.text()
                        logger.warning(f"Model {m} returned {resp.status}: {err_text[:150]}")
            except Exception as e:
                logger.error(f"Error querying model {m}: {e}")

        return None

    async def handle_message(self, msg: Dict[str, Any]):
        """Обрабатывает входящее сообщение."""
        user = msg.get("from", {})
        user_id = user.get("id")
        chat_id = msg.get("chat", {}).get("id")
        msg_id = msg.get("message_id")

        if not user_id or not chat_id:
            return

        # Проверка прав: только администраторы
        if user_id not in self.admin_ids:
            logger.warning(f"Unauthorized attempt from user_id: {user_id} (@{user.get('username')})")
            await self.send_message(
                chat_id,
                "⛔️ <b>Доступ запрещен.</b>\nЭтот бот предназначен исключительно для администраторов Skyrex Computers.",
                reply_to_message_id=msg_id
            )
            return

        text = msg.get("text", "").strip()

        # Команды
        if text == "/start" or text == "/help":
            await self.send_message(
                chat_id,
                "👋 <b>Бот-расшифровщик голосовых сообщений Skyrex</b>\n\n"
                "📌 <b>Как пользоваться:</b>\n"
                "1. Перешлите сюда любое <b>голосовое сообщение</b>, <b>аудиозапись</b> или <b>видеосообщение (кружочек)</b> от заказчика/клиента.\n"
                "2. Бот мгновенно скачает аудио, распознает речь через нейросеть Gemini и пришлет вам чистый структурированный текст с сохранением всех моделей комплектующих, цен и деталей заказа.\n"
                "3. Вы также можете записывать и отправлять собственные голосовые заметки.",
                reply_to_message_id=msg_id
            )
            return

        # Определение типа аудио-вложения
        voice = msg.get("voice")
        audio = msg.get("audio")
        video_note = msg.get("video_note")
        media = voice or audio or video_note

        if not media:
            await self.send_message(
                chat_id,
                "🎙 <b>Перешлите голосовое сообщение от заказчика</b>, и я расшифрую его в текст.",
                reply_to_message_id=msg_id
            )
            return

        # Определение типа медиа
        if video_note:
            media_label = "видеосообщение (кружочек)"
            icon = "📹"
            mime_type = "video/mp4"
        elif audio:
            media_label = "аудиозапись"
            icon = "🎵"
            mime_type = audio.get("mime_type", "audio/mp3")
        else:
            media_label = "голосовое сообщение"
            icon = "🎙"
            mime_type = voice.get("mime_type", "audio/ogg")

        # Нормализация MIME-типа для Gemini
        if "ogg" in mime_type or "oga" in mime_type or "opus" in mime_type:
            mime_type = "audio/ogg"
        elif "mp3" in mime_type or "mpeg" in mime_type:
            mime_type = "audio/mp3"
        elif "wav" in mime_type:
            mime_type = "audio/wav"

        # Отправляем предварительный статус
        status_res = await self.send_message(
            chat_id,
            f"{icon} <i>Слушаю и расшифровываю {media_label}...</i>",
            reply_to_message_id=msg_id
        )
        status_msg_id = status_res.get("result", {}).get("message_id")
        await self.send_chat_action(chat_id, "typing")

        try:
            # 1. Сбор метаданных об отправителе
            sender_parts = []
            if msg.get("forward_from"):
                fwd = msg["forward_from"]
                name = f"{fwd.get('first_name', '')} {fwd.get('last_name', '')}".strip()
                if fwd.get("username"):
                    name += f" (@{fwd['username']})"
                sender_parts.append(name)
            elif msg.get("forward_sender_name"):
                sender_parts.append(msg["forward_sender_name"])
            elif msg.get("forward_date"):
                sender_parts.append("Заказчик (скрытый профиль)")
            else:
                sender_parts.append(f"{user.get('first_name', '')} (прямая запись)")

            sender_name = " ".join(sender_parts).strip() or "Заказчик"

            # Длительность
            duration = media.get("duration", 0)
            duration_str = f"{duration // 60}:{duration % 60:02d}"

            # Дата исходного сообщения при пересылке
            date_str = ""
            fwd_date = msg.get("forward_date")
            if fwd_date:
                dt = datetime.datetime.fromtimestamp(fwd_date)
                date_str = f" • <i>{dt.strftime('%d.%m.%Y %H:%M')}</i>"

            # 2. Скачивание файла
            file_id = media.get("file_id")
            audio_bytes = await self.download_telegram_file(file_id)

            if not audio_bytes:
                err_msg = "❌ Не удалось загрузить аудиофайл из Telegram."
                if status_msg_id:
                    await self.edit_message(chat_id, status_msg_id, err_msg)
                else:
                    await self.send_message(chat_id, err_msg, reply_to_message_id=msg_id)
                return

            # 3. Расшифровка через Gemini
            transcript = await self.transcribe_with_gemini(audio_bytes, mime_type=mime_type)

            if not transcript:
                err_msg = "⚠️ Не удалось распознать речь (возможно, запись слишком тихая или слышен только шум)."
                if status_msg_id:
                    await self.edit_message(chat_id, status_msg_id, err_msg)
                else:
                    await self.send_message(chat_id, err_msg, reply_to_message_id=msg_id)
                return

            # 4. Формирование ответа
            header = (
                f"{icon} <b>Расшифровка {media_label}</b>\n\n"
                f"👤 <b>Клиент / Источник:</b> {html.escape(sender_name)}{date_str}\n"
                f"⏱ <b>Длительность:</b> {duration_str}\n"
            )

            caption = msg.get("caption")
            if caption:
                header += f"💬 <b>Подпись к сообщению:</b> <i>{html.escape(caption)}</i>\n"

            header += "──────────────────────────\n\n"

            full_reply = header + html.escape(transcript)

            # Удаляем временное сообщение со статусом
            if status_msg_id:
                await self.delete_message(chat_id, status_msg_id)

            # Отправка результата (с разбивкой на части, если текст > 4000 символов)
            if len(full_reply) <= 4000:
                await self.send_message(chat_id, full_reply, reply_to_message_id=msg_id)
            else:
                await self.send_message(chat_id, header, reply_to_message_id=msg_id)
                for i in range(0, len(transcript), 3800):
                    part = transcript[i:i + 3800]
                    await self.send_message(chat_id, html.escape(part))

            logger.info(f"✅ Успешно расшифровано сообщение от {sender_name} ({duration_str}) для чата {chat_id}")

        except Exception as e:
            logger.error(f"Ошибка при обработке голосового сообщения: {e}", exc_info=True)
            err_msg = f"❌ Произошла ошибка при расшифровке: {e}"
            if status_msg_id:
                await self.edit_message(chat_id, status_msg_id, err_msg)
            else:
                await self.send_message(chat_id, err_msg, reply_to_message_id=msg_id)

    async def get_updates(self, offset: int = 0, timeout: int = 25) -> List[Dict[str, Any]]:
        """Получает новые обновления от Telegram."""
        res = await self.api_request("getUpdates", {"offset": offset, "timeout": timeout})
        if res.get("ok"):
            return res.get("result", [])
        return []

    async def start(self):
        """Запуск цикла Long Polling."""
        if not self.token:
            logger.error("❌ TG_BOT_TOKEN не задан в .env файле!")
            return
        if not self.admin_ids:
            logger.error("❌ TG_ADMIN_IDS не задан в .env файле!")
            return

        self.is_running = True
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))

        me = await self.api_request("getMe")
        if not me.get("ok"):
            logger.error(f"❌ Ошибка подключения бота: {me.get('description')}")
            return

        bot_username = me.get("result", {}).get("username", "Unknown")
        logger.info(f"============================================================")
        logger.info(f"🚀 Voice Transcriber Bot запущен как @{bot_username}")
        logger.info(f"👥 Разрешенные администраторы: {self.admin_ids}")
        logger.info(f"🧠 Модель распознавания: {LLM_MODEL}")
        logger.info(f"============================================================")

        offset = 0
        while self.is_running:
            try:
                updates = await self.get_updates(offset=offset, timeout=25)
                for u in updates:
                    offset = max(offset, u.get("update_id", 0) + 1)
                    if "message" in u:
                        await self.handle_message(u["message"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле polling: {e}")
                await asyncio.sleep(3)

        if self.session and not self.session.closed:
            await self.session.close()


if __name__ == "__main__":
    bot = VoiceTranscriberBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print("\n[!] Бот остановлен администратором.")

