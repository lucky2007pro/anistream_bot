"""
Majburiy obuna tekshirish middleware
"""
from typing import Callable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError
from database.db import get_required_channels, is_admin


def _chat_id_value(raw: str) -> str | int:
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


async def get_missing_channels(bot, user_id: int) -> list[dict]:
    channels = await get_required_channels()
    if not channels:
        return []

    missing = []
    for channel in channels:
        channel_id = channel.get("channel_id", "")
        if not channel_id:
            continue
        try:
            member = await bot.get_chat_member(_chat_id_value(str(channel_id)), user_id)
            if member.status in ("left", "kicked", "banned"):
                missing.append(channel)
        except TelegramAPIError:
            # API vaqtinchalik xatolarida foydalanuvchini bloklamaymiz.
            continue
    return missing


async def check_subscribed(bot, user_id: int) -> bool:
    missing = await get_missing_channels(bot, user_id)
    return len(missing) == 0


class SubscribeMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if not user or user.is_bot:
            return await handler(event, data)

        # Adminlar uchun tekshirmaslik
        if await is_admin(user.id):
            return await handler(event, data)

        bot = data.get("bot")
        missing = await get_missing_channels(bot, user.id)
        if missing:
            from utils.keyboards import subscribe_kb
            lines = ["📢 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>", ""]
            for i, channel in enumerate(missing, 1):
                title = channel.get("title") or channel.get("channel_id") or "Kanal"
                lines.append(f"{i}. {title}")
            lines.append("")
            lines.append("Obuna bo'lgach <b>✅ Tekshirish</b> ni bosing.")
            text = "\n".join(lines)

            if isinstance(event, Message):
                await event.answer(text, parse_mode="HTML",
                                   reply_markup=subscribe_kb(missing))
            elif isinstance(event, CallbackQuery):
                await event.answer("❗ Avval kanalga obuna bo'ling!", show_alert=True)
                await event.message.answer(text, parse_mode="HTML",
                                           reply_markup=subscribe_kb(missing))
            return
        return await handler(event, data)
