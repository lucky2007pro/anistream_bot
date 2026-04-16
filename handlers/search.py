"""
Qidirish — lokal baza + AniList API
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from api.anilist import (
    search_anime, get_trending, get_top, get_seasonal,
    get_details, format_card, format_list_item, get_title,
)
from database.db import (
    search_local_anime, get_anime_by_anilist,
    get_top_anime_local, get_most_viewed, log_action,
)
from utils.keyboards import (
    search_results_kb, local_anime_list_kb,
    anime_card_kb, get_main_kb, cancel_kb,
)
from config import RESULTS_PER_PAGE

router = Router()


class SearchState(StatesGroup):
    waiting = State()


MENU_BUTTONS = {
    "🔥 Trending", "🏆 Top anime", "🌸 Mavsumiy",
    "🎲 Tasodifiy", "❤️ Sevimlilar", "📜 Tarixim",
    "👤 Profilim", "🆘 Yordam", "🎬 Barcha animalar",
    "➕ Anime qo'shish", "📤 Epizod yuklash", "💬 Izohlar",
    "📊 Admin panel", "📢 Broadcast", "⚙️ Sozlamalar", "🔽 Menyuni yopish",
    "☰ Menyuni ochish", "❌ Bekor qilish",
}


@router.message(F.text == "🔍 Qidirish")
async def search_btn(msg: Message, state: FSMContext):
    await state.set_state(SearchState.waiting)
    await msg.answer(
        "🔍 <b>Anime qidirish</b>\n\n"
        "Anime nomini kiriting (Ingliz, Yapon yoki O'zbek tilida):\n\n"
        "<i>Misol: Naruto, One Piece, Demon Slayer</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(SearchState.waiting, F.text)
async def search_state(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=await get_main_kb(msg.from_user.id))
        return
    await state.clear()
    await msg.answer("👍", reply_markup=await get_main_kb(msg.from_user.id))
    await _do_search(msg, msg.text.strip())


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(MENU_BUTTONS))
async def search_text(msg: Message):
    await _do_search(msg, msg.text.strip())


async def _do_search(msg: Message, query: str):
    if len(query) < 2:
        await msg.answer("❗ Kamida 2 ta harf kiriting")
        return

    await log_action(msg.from_user.id, "search", query)
    wait = await msg.answer("🔍 Qidirilmoqda...")

    # 1) Lokal bazadan qidirish
    local = await search_local_anime(query)

    # 2) AniList dan qidirish
    anilist_result = await search_anime(query, page=1, per_page=RESULTS_PER_PAGE)
    await wait.delete()

    # Lokal natijalar bor bo'lsa
    if local:
        text = f"🔍 <b>Natijalar:</b> <i>{query}</i>\n\n"
        text += "📦 <b>Botda mavjud:</b>\n"
        for i, a in enumerate(local, 1):
            t = a.get("title_en") or a.get("title_jp") or "?"
            ep = a.get("total_ep",0)
            text += f"{i}. 🎌 <b>{t}</b> ({ep} ep)\n"

        kb = local_anime_list_kb(local, 1, 1, "all_anime")

        # AniList ham ko'rsatish
        if anilist_result and anilist_result.get("media"):
            text += "\n🌐 <b>AniList da ham topildi:</b>\n"
            for i, a in enumerate(anilist_result["media"], 1):
                text += format_list_item(a, i) + "\n"
            media = anilist_result["media"]
            total = anilist_result.get("pageInfo",{}).get("total", len(media))
            total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
            kb = search_results_kb(media, 1, total_pages, query)

        cover = local[0].get("cover_image","") if local else ""
        if cover:
            await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            await msg.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    # Faqat AniList natija
    if not anilist_result or not anilist_result.get("media"):
        await msg.answer(
            f"😔 <b>'{query}'</b> bo'yicha hech narsa topilmadi.\n"
            "💡 Ingliz yoki yapon tilida yozib ko'ring.",
            parse_mode="HTML",
        )
        return

    media = anilist_result["media"]
    total = anilist_result.get("pageInfo",{}).get("total", len(media))
    total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)

    text = f"🔍 <b>AniList natijalar:</b> <i>{query}</i>\n\n"
    for i, a in enumerate(media, 1):
        text += format_list_item(a, i) + "\n"
    text += "\n<i>💡 Bu animeni botga qo'shish uchun adminga yozing</i>"

    cover = (media[0].get("coverImage") or {}).get("large","") if media else ""
    kb = search_results_kb(media, 1, total_pages, query)
    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.regexp(r"^srch:.+:\d+$"))
async def search_page(cb: CallbackQuery):
    await cb.answer()
    _, query, page_str = cb.data.split(":", 2)
    page = int(page_str)
    result = await search_anime(query, page=page, per_page=RESULTS_PER_PAGE)
    if not result or not result.get("media"):
        await cb.answer("❌ Natija yo'q", show_alert=True)
        return
    media = result["media"]
    total = result.get("pageInfo",{}).get("total", len(media))
    total_pages = max(1, (total + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE)
    text = f"🔍 <b>Natijalar:</b> <i>{query}</i> — {page}/{total_pages}\n\n"
    for i, a in enumerate(media, (page-1)*RESULTS_PER_PAGE+1):
        text += format_list_item(a, i) + "\n"
    kb = search_results_kb(media, page, total_pages, query)
    try:
        await cb.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# AniList animeni ko'rsatish
@router.callback_query(F.data.regexp(r"^anilist:\d+$"))
async def show_anilist_anime(cb: CallbackQuery):
    await cb.answer()
    anilist_id = int(cb.data.split(":")[1])

    # Avval lokal bazadan tekshirish
    local = await get_anime_by_anilist(anilist_id)
    if local:
        from handlers.anime import show_local_anime
        await show_local_anime(cb, local["id"], cb.from_user.id)
        return

    # AniList dan olish
    anime = await get_details(anilist_id)
    if not anime:
        await cb.answer("❌ Anime topilmadi", show_alert=True)
        return

    text = format_card(anime)
    text += "\n\n<i>⚠️ Bu anime hali botga qo'shilmagan\nAdmin qo'shgandan so'ng ko'rish mumkin</i>"
    cover = (anime.get("coverImage") or {}).get("extraLarge") or (anime.get("coverImage") or {}).get("large","")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🌐 AniList", url=f"https://anilist.co/anime/{anilist_id}"))

    try:
        if cover:
            await cb.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=b.as_markup())
        else:
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())
    except Exception:
        if cover:
            await cb.message.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=b.as_markup())


# Trending, Top, Seasonal
@router.message(F.text == "🔥 Trending")
async def trending(msg: Message):
    items = await get_trending(1)
    if not items:
        await msg.answer("❌ Ma'lumot yuklanmadi"); return
    text = "🔥 <b>Bugungi Trend Animalar</b>\n\n"
    for i, a in enumerate(items, 1):
        text += format_list_item(a, i) + "\n"
    cover = (items[0].get("coverImage") or {}).get("large","")
    from utils.keyboards import InlineKeyboardBuilder, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    from aiogram.types import InlineKeyboardButton as IKBt
    b = IKB()
    for a in items[:10]:
        t = get_title(a)
        t = (t[:33]+"…") if len(t)>33 else t
        b.row(IKBt(text=f"🎌 {t}", callback_data=f"anilist:{a['id']}"))
    kb = b.as_markup()
    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(F.text == "🏆 Top anime")
async def top_cmd(msg: Message):
    # Avval lokal top
    local_top = await get_top_anime_local(10)
    items = await get_top(1)

    if local_top:
        text = "🏆 <b>Botdagi Top Anime</b> (reyting bo'yicha)\n\n"
        for i, a in enumerate(local_top, 1):
            t = a.get("title_en") or a.get("title_jp") or "?"
            rating = round(a.get("avg_rating",0), 1)
            votes = a.get("vote_count",0)
            text += f"{i}. <b>{t}</b> ⭐{rating} ({votes} ovoz)\n"
        kb = local_anime_list_kb(local_top, 1, 1, "all_anime")
        cover = local_top[0].get("cover_image","") if local_top else ""
        if cover:
            await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            await msg.answer(text, parse_mode="HTML", reply_markup=kb)
    elif items:
        text = "🏆 <b>Top Anime (AniList)</b>\n\n"
        for i, a in enumerate(items, 1):
            text += format_list_item(a, i) + "\n"
        await msg.answer(text, parse_mode="HTML")


@router.message(F.text == "🌸 Mavsumiy")
async def seasonal(msg: Message):
    items = await get_seasonal(1)
    if not items:
        await msg.answer("❌ Ma'lumot yuklanmadi"); return
    text = "🌸 <b>Joriy Mavsum Animelari</b>\n\n"
    for i, a in enumerate(items, 1):
        text += format_list_item(a, i) + "\n"
    cover = (items[0].get("coverImage") or {}).get("large","")
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    from aiogram.types import InlineKeyboardButton as IKBt
    b = IKB()
    for a in items[:10]:
        t = get_title(a)
        t = (t[:33]+"…") if len(t)>33 else t
        b.row(IKBt(text=f"🎌 {t}", callback_data=f"anilist:{a['id']}"))
    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.message(F.text == "🎲 Tasodifiy")
async def random_cmd(msg: Message):
    import random
    items = await get_all_anime(1, 100)
    if not items:
        await msg.answer("😔 Botda hali anime yo'q")
        return
    anime = random.choice(items)
    from handlers.anime import show_local_anime
    await show_local_anime(msg, anime["id"], msg.from_user.id)
