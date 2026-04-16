from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from database.db import get_stats, log_action, register_user
from utils.keyboards import get_main_kb, reopen_kb
from middlewares.subscribe import check_subscribed

router = Router()

WELCOME = (
    "🎌 <b>Anime Bot</b>\n\n"
    "Salom, <b>{name}</b>! 👋\n\n"
    "Bu yerda siz:\n"
    "📺 Anime ko'rishingiz\n"
    "📥 Epizodlarni yuklab olishingiz\n"
    "❤️ Sevimlilar ro'yxati yuritishingiz\n"
    "⭐ Reyting berishingiz mumkin!\n\n"
    "👇 Pastki menyudan boshlang:"
)

HELP = (
    "🆘 <b>Yordam</b>\n\n"
    "🔍 <b>Qidirish</b> — Anime nomini yuboring\n"
    "🎬 <b>Barcha animalar</b> — Botdagi animalar\n"
    "🔥 <b>Trending</b> — Trend animalar\n"
    "🏆 <b>Top anime</b> — Reytingli animalar\n"
    "❤️ <b>Sevimlilar</b> — Saqlangan animalar\n"
    "📜 <b>Tarixim</b> — Ko'rilgan epizodlar\n"
    "👤 <b>Profilim</b> — Statistika va ma'lumotlar\n\n"
    "📤 <b>Epizod yuklash:</b>\n"
    "Anime → 📺 Epizodlar → ▶️ Epizodni tanlang\n\n"
    "🔔 <b>Bildirishnoma:</b>\n"
    "Anime kartasida '🔔 Yangi epizod xabari' tugmasi"
)


@router.message(CommandStart())
async def start(msg: Message):
    args = msg.text.split()
    ref_by = 0
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_by = int(args[1].split("_")[1])
        except Exception:
            pass

    await register_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.first_name or "",
        ref_by
    )
    await log_action(msg.from_user.id, "start")

    name = msg.from_user.first_name or "Foydalanuvchi"
    await msg.answer_photo(
        photo="https://i.imgur.com/Hurzkvf.jpeg",
        caption=WELCOME.format(name=name),
        parse_mode="HTML",
    )
    await msg.answer(
        "👇 Menyudan foydalaning:",
        reply_markup=await get_main_kb(msg.from_user.id),
    )


@router.message(Command("menu"))
@router.message(F.text == "☰ Menyuni ochish")
async def open_menu(msg: Message):
    await msg.answer("📋 Menyu ochildi!", reply_markup=await get_main_kb(msg.from_user.id))


@router.message(F.text == "🔽 Menyuni yopish")
async def close_menu(msg: Message):
    from aiogram.types import ReplyKeyboardRemove
    await msg.answer(
        "✅ Menyu yopildi. Qayta ochish: /menu",
        reply_markup=reopen_kb(),
    )


@router.message(Command("help"))
@router.message(F.text == "🆘 Yordam")
async def help_cmd(msg: Message):
    await msg.answer(HELP, parse_mode="HTML")


# ── Majburiy obuna tekshirish ──────────────────────────────────
@router.callback_query(F.data == "check_subscribe")
async def check_sub_cb(cb: CallbackQuery):
    ok = await check_subscribed(cb.bot, cb.from_user.id)
    if ok:
        await cb.answer("✅ Tasdiqlandi! Botdan foydalanishingiz mumkin.", show_alert=True)
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(
            "✅ Obuna tasdiqlandi!\n\n🎌 Botdan foydalanishingiz mumkin.",
            reply_markup=await get_main_kb(cb.from_user.id),
        )
    else:
        await cb.answer("❌ Siz hali obuna bo'lmagansiz!", show_alert=True)


@router.callback_query(F.data == "noop")
async def noop(cb: CallbackQuery):
    await cb.answer()
