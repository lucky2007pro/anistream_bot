"""
Soddalashtirilgan qidiruv - faqat lokal baza
"""
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import search_local_anime, log_action
from utils.keyboards import search_results_kb, get_main_kb, cancel_kb

router = Router()


class SearchState(StatesGroup):
    waiting = State()


@router.message(F.text == "🔍 Qidirish")
async def search_btn(msg: Message, state: FSMContext):
    await state.set_state(SearchState.waiting)
    await msg.answer(
        "🔍 Anime nomini kiriting:\n"
        "Misol: Naruto",
        reply_markup=cancel_kb(),
    )


@router.message(SearchState.waiting, F.text)
async def search_state(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=await get_main_kb(msg.from_user.id))
        return

    await state.clear()
    query = msg.text.strip()
    if len(query) < 2:
        await msg.answer("❗ Kamida 2 ta harf kiriting", reply_markup=await get_main_kb(msg.from_user.id))
        return

    await _do_local_search(msg, query)


async def _do_local_search(msg: Message, query: str):
    await log_action(msg.from_user.id, "search", query)
    items = await search_local_anime(query)

    if not items:
        await msg.answer("😔 Topilmadi", reply_markup=await get_main_kb(msg.from_user.id))
        return

    text = f"🔍 <b>Natijalar:</b> <i>{query}</i>\n\n"
    for i, a in enumerate(items[:10], 1):
        t = a.get("title_en") or a.get("title_jp") or "?"
        ep = a.get("total_ep", 0)
        text += f"{i}. <b>{t}</b> | ID: <code>{a['id']}</code> | {ep} ep\n"

    kb = search_results_kb(items[:10], 1, 1, query)
    cover = items[0].get("cover_image", "")

    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)
