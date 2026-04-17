"""
Register middleware — in-memory cache bilan optimallashtirilgan.
Foydalanuvchini faqat birinchi marta yoki 5 daqiqada bir marta bazaga yozadi.
"""
import time
from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from database.db import register_user

# In-memory cache: {user_id: last_update_timestamp}
_user_cache: dict[int, float] = {}
_CACHE_TTL = 300  # 5 daqiqa


class RegisterMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user: User | None = data.get("event_from_user")
        if user and not user.is_bot:
            now = time.time()
            last = _user_cache.get(user.id, 0)
            if now - last > _CACHE_TTL:
                await register_user(user.id, user.username or "", user.first_name or "", 0)
                _user_cache[user.id] = now
        return await handler(event, data)
