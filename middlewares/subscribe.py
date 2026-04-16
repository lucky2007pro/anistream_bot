"""
Majburiy obuna tekshirish middleware
"""
from typing import Callable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError
from database.db import get_setting, is_admin


def _chat_id_value(raw: str) -> str | int:
    raw = (raw or "").strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


async def check_subscribed(bot, user_id: int) -> bool:
    subscribe_channel_id = await get_setting("subscribe_channel_id", "")
    if not subscribe_channel_id:
        return True
    try:
        member = await bot.get_chat_member(_chat_id_value(subscribe_channel_id), user_id)
        return member.status not in ("left", "kicked", "banned")
    except TelegramAPIError:
        return True  # Tekshirib bo'lmasa ruxsat ber


class SubscribeMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user = data.get("event_from_user")
        if not user or user.is_bot:
            return await handler(event, data)

        # Adminlar uchun tekshirmaslik
        if await is_admin(user.id):
            return await handler(event, data)

        bot = data.get("bot")
        if not await check_subscribed(bot, user.id):
            from utils.keyboards import subscribe_kb
            subscribe_channel = await get_setting("subscribe_channel", "")
            text = (
                f"📢 <b>Botdan foydalanish uchun kanalga obuna bo'ling!</b>\n\n"
                f"Kanal: {subscribe_channel or '@kanal_username'}\n\n"
                f"Obuna bo'lgandan so'ng <b>✅ Tekshirish</b> tugmasini bosing."
            )
            if isinstance(event, Message):
                await event.answer(text, parse_mode="HTML",
                                   reply_markup=subscribe_kb(subscribe_channel))
            elif isinstance(event, CallbackQuery):
                await event.answer("❗ Avval kanalga obuna bo'ling!", show_alert=True)
                await event.message.answer(text, parse_mode="HTML",
                                           reply_markup=subscribe_kb(subscribe_channel))
            return
        return await handler(event, data)
