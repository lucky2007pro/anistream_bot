from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from database.db import register_user


class RegisterMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: TelegramObject, data: dict) -> Any:
        user: User | None = data.get("event_from_user")
        if user and not user.is_bot:
            # start parametridan ref_id olish
            ref_by = 0
            msg = data.get("event_update", {})
            await register_user(user.id, user.username or "", user.first_name or "", ref_by)
        return await handler(event, data)
