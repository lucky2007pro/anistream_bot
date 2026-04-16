from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import log_action, register_user
from utils.keyboards import get_main_kb, reopen_kb, subscribe_kb
from middlewares.subscribe import check_subscribed, get_missing_channels

router = Router()


class OpenByIdState(StatesGroup):
    waiting = State()


WELCOME = (
    "🎌 <b>Anime Bot</b>\n\n"
    "Salom, <b>{name}</b>! 👋\n"
    "Anime ko'rish uchun qidiruvdan yoki ID orqali foydalaning."
)

HELP = (
    "🆘 <b>Yordam</b>\n\n"
    "🔍 <b>Qidirish</b> — nom bo'yicha qidirish\n"
    "🎬 <b>Barcha animelar</b> — katalog\n"
    "🆔 <b>ID bo'yicha ochish</b> — aniq anime ochish\n"
)


@router.message(CommandStart())
async def start(msg: Message):
    args = msg.text.split()
    ref_by = 0
    deep = args[1] if len(args) > 1 else ""

    if deep.startswith("ref_"):
        try:
            ref_by = int(deep.split("_", 1)[1])
        except Exception:
            ref_by = 0

    await register_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.first_name or "",
        ref_by,
    )
    await log_action(msg.from_user.id, "start")

    # Deep-link: anime_12
    if deep.startswith("anime_"):
        from handlers.anime import show_local_anime

        tail = deep.split("_", 1)[1]
        if tail.isdigit():
            await show_local_anime(msg, int(tail), msg.from_user.id)
            await msg.answer("👇 Menyu:", reply_markup=await get_main_kb(msg.from_user.id))
            return

    name = msg.from_user.first_name or "Foydalanuvchi"
    await msg.answer(WELCOME.format(name=name), parse_mode="HTML")
    await msg.answer("👇 Menyudan foydalaning:", reply_markup=await get_main_kb(msg.from_user.id))


@router.message(Command("menu"))
@router.message(F.text == "☰ Menyuni ochish")
async def open_menu(msg: Message):
    await msg.answer("📋 Menyu ochildi", reply_markup=await get_main_kb(msg.from_user.id))


@router.message(F.text == "🔽 Menyuni yopish")
async def close_menu(msg: Message):
    await msg.answer("✅ Menyu yopildi", reply_markup=reopen_kb())


@router.message(Command("help"))
@router.message(F.text == "🆘 Yordam")
async def help_cmd(msg: Message):
    await msg.answer(HELP, parse_mode="HTML")


@router.message(F.text == "🆔 ID bo'yicha ochish")
async def open_by_id_prompt(msg: Message, state: FSMContext):
    await state.set_state(OpenByIdState.waiting)
    await msg.answer("Anime ID kiriting:\nMisol: <code>12</code>", parse_mode="HTML")


@router.message(OpenByIdState.waiting, F.text)
async def open_by_id(msg: Message, state: FSMContext):
    if not msg.text.strip().isdigit():
        await msg.answer("❗ Faqat raqam kiriting")
        return

    await state.clear()
    anime_id = int(msg.text.strip())
    from handlers.anime import show_local_anime

    await show_local_anime(msg, anime_id, msg.from_user.id)


@router.callback_query(F.data == "check_subscribe")
async def check_sub_cb(cb: CallbackQuery):
    ok = await check_subscribed(cb.bot, cb.from_user.id)
    if ok:
        await cb.answer("✅ Tasdiqlandi", show_alert=True)
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer("✅ Endi botdan foydalanishingiz mumkin", reply_markup=await get_main_kb(cb.from_user.id))
    else:
        missing = await get_missing_channels(cb.bot, cb.from_user.id)
        lines = ["❌ Siz hali quyidagi kanallarga obuna bo'lmagansiz:", ""]
        for i, channel in enumerate(missing, 1):
            title = channel.get("title") or channel.get("channel_id") or "Kanal"
            lines.append(f"{i}. {title}")
        await cb.answer("❌ Hali obuna bo'lmagansiz", show_alert=True)
        await cb.message.answer("\n".join(lines), reply_markup=subscribe_kb(missing))


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()
