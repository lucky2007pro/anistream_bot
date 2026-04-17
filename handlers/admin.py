"""
Soddalashtirilgan admin panel:
- Anime qo'shish (nom, janr, turi, rasm)
- Epizod yuklash
- Ulangan kanallarni boshqarish
- Root admin: delegat admin qo'shish/o'chirish
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
import html
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    add_anime, get_anime_by_id, delete_anime,
    add_episode, get_episodes, get_episode, delete_episode,
    get_stats, log_action, search_local_anime,
    is_admin as db_is_admin, is_root_admin,
    add_delegated_admin, remove_delegated_admin, list_delegated_admins,
    add_publish_channel, remove_publish_channel, get_publish_channels,
    get_publish_channel, update_publish_channel,
    get_all_anime, get_total_anime_count,
    update_anime_fields, set_anime_active,
    approve_comment, get_pending_comments,
)
from utils.keyboards import admin_kb, cancel_kb, admin_ep_list_kb

router = Router()


async def is_admin(uid: int) -> bool:
    return await db_is_admin(uid)


class AddAnimeState(StatesGroup):
    title = State()
    genres = State()
    kind = State()
    cover = State()


class UploadEpState(StatesGroup):
    select_anime = State()
    ep_number = State()
    upload_video = State()


class ChannelState(StatesGroup):
    add_channel = State()
    edit_channel = State()
    toggle_required = State()
    remove_channel = State()


class AdminManageState(StatesGroup):
    waiting_add = State()
    waiting_remove = State()


class EditAnimeState(StatesGroup):
    title = State()
    genres = State()
    status = State()
    cover = State()



@router.callback_query(F.data.regexp(r"^anime_kind:(MOVIE|SERIAL)$"))
async def add_anime_kind(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    kind = cb.data.split(":", 1)[1]
    await state.update_data(kind=kind)
    await state.set_state(AddAnimeState.cover)
    await cb.answer()
    await cb.message.answer(
        "Endi anime rasmi yuboring yoki <b>⏭ O'tkazib yuborish</b> deb yozing.",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(AddAnimeState.cover, F.photo)
async def add_anime_cover(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    cover_file_id = msg.photo[-1].file_id
    anime_id = await add_anime({
        "title_en": data.get("title", ""),
        "title_jp": "",
        "title_uz": "",
        "description": "",
        "genres": data.get("genres", ""),
        "status": data.get("kind", "SERIAL"),
        "cover_image": cover_file_id,
        "total_ep": 0,
        "added_by": msg.from_user.id,
    })

    await msg.answer_photo(
        photo=cover_file_id,
        caption=(
            f"✅ Anime qo'shildi\n"
            f"🆔 ID: <code>{anime_id}</code>\n"
            f"🎌 Nomi: <b>{data.get('title', '?')}</b>\n"
            f"🎭 Janr: {data.get('genres', '-') }\n"
            f"📁 Turi: {data.get('kind', 'SERIAL')}"
        ),
        parse_mode="HTML",
        reply_markup=admin_kb(),
    )


@router.message(AddAnimeState.cover, F.text)
async def add_anime_skip_cover(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    if msg.text.strip().lower() not in {"⏭ o'tkazib yuborish", "otkaz", "skip"}:
        await msg.answer("Rasm yuboring yoki '⏭ O'tkazib yuborish' deb yozing")
        return

    data = await state.get_data()
    await state.clear()
    anime_id = await add_anime({
        "title_en": data.get("title", ""),
        "title_jp": "",
        "title_uz": "",
        "description": "",
        "genres": data.get("genres", ""),
        "status": data.get("kind", "SERIAL"),
        "cover_image": "",
        "total_ep": 0,
        "added_by": msg.from_user.id,
    })
    await msg.answer(
        f"✅ Anime qo'shildi\nID: <code>{anime_id}</code>",
        parse_mode="HTML",
        reply_markup=admin_kb(),
    )

# ===================== Epizod yuklash =====================
async def show_anime_episodes_for_upload(msg_obj, anime, state: FSMContext, edit=False):
    anime_id = anime["id"]
    await state.update_data(anime_id=anime_id)
    
    eps = await get_episodes(anime_id)
    ep_list = ", ".join([str(e["ep_number"]) for e in eps]) if eps else "Yo'q"
    
    title = anime.get("title_en") or anime.get("title_jp") or "?"
    text = (
        f"🎌 <b>{title}</b> (ID: {anime_id})\n"
        f"📁 Status: {anime.get('status', 'SERIAL')}\n"
        f"📺 Mavjud epizodlar: {ep_list}\n\n"
        "👇 Qanday amal bajaramiz?"
    )
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    
    if (anime.get("status") or "").upper() == "MOVIE":
        b.row(InlineKeyboardButton(text="🎬 Filmni yuklash", callback_data=f"up_movie:{anime_id}"))
    else:
        b.row(InlineKeyboardButton(text="➕ Yangi qism yuklash", callback_data=f"up_ep:{anime_id}"))
        
    b.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_upload_ep"))
    
    if edit:
        try:
            await msg_obj.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())
        except:
            await msg_obj.answer(text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await msg_obj.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.message(F.text == "📤 Epizod yuklash")
@router.callback_query(F.data.regexp(r"^admin_upload_ep(?::\d+)?$"))
async def upload_ep_start(event, state: FSMContext):
    if not await is_admin(event.from_user.id):
        if isinstance(event, CallbackQuery):
            await event.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    page = 1
    if isinstance(event, CallbackQuery):
        parts = event.data.split(":")
        if len(parts) > 1:
            page = int(parts[1])
        await event.answer()

    items = await get_all_anime(page=page, per_page=10, include_inactive=True)
    total = await get_total_anime_count(include_inactive=True)
    total_pages = max(1, (total + 10 - 1) // 10)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    
    for a in items:
        t = a.get("title_en") or a.get("title_jp") or "?"
        t = (t[:35] + "...") if len(t) > 35 else t
        b.row(InlineKeyboardButton(text=f"📺 {t}", callback_data=f"ep_sel_anime:{a['id']}"))

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin_upload_ep:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin_upload_ep:{page+1}"))
    if nav:
        b.row(*nav)

    text = (
        "📤 <b>Epizod yuklash</b>\n\n"
        "Quyidagi ro'yxatdan animeni tanlang yoki izlash uchun "
        "uning <b>ID raqamini</b> yoxud <b>nomini</b> tepadagi menyudan kriting:"
    )
    
    await state.set_state(UploadEpState.select_anime)
    
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        try:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=b.as_markup())
        except:
            await event.message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.message(UploadEpState.select_anime, F.text)
async def upload_select_anime(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    query = msg.text.strip()
    anime = None

    if query.isdigit():
        anime = await get_anime_by_id(int(query))
        if anime:
            return await show_anime_episodes_for_upload(msg, anime, state)
    else:
        results = await search_local_anime(query)
        if len(results) == 1:
            return await show_anime_episodes_for_upload(msg, results[0], state)
        elif len(results) > 1:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            b = InlineKeyboardBuilder()
            for a in results[:8]:
                t = a.get("title_en") or "?"
                b.row(InlineKeyboardButton(text=f"{t} (ID:{a['id']})", callback_data=f"ep_sel_anime:{a['id']}"))
            await msg.answer("🔍 Bir nechta anime topildi. Qaysi biri?", reply_markup=b.as_markup())
            return

    await msg.answer("❌ Topilmadi. Boshqa so'z kiriting yoki ro'yxatdan tanlang:")


@router.callback_query(F.data.regexp(r"^ep_sel_anime:\d+$"))
async def ep_sel_anime_cb(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)
    if not anime:
        await cb.answer("❌ Anime topilmadi", show_alert=True)
        return
        
    await cb.answer()
    await show_anime_episodes_for_upload(cb.message, anime, state, edit=True)


@router.callback_query(F.data.regexp(r"^up_movie:\d+$"))
async def up_movie_cb(cb: CallbackQuery, state: FSMContext):
    anime_id = int(cb.data.split(":")[1])
    existing = await get_episode(anime_id, 1)
    if existing:
        await cb.answer("❗ Bu film uchun video allaqachon yuklangan!\nEskisini o'chirmaguncha yangisini yuklay olmaysiz.", show_alert=True)
        return
        
    await state.update_data(anime_id=anime_id, ep_number=1)
    await state.set_state(UploadEpState.upload_video)
    await cb.answer()
    await cb.message.answer(
        "🎬 Film uchun video yuboring:\n(Ushbu amalni to'xtatish uchun bot pastidagi '❌ Bekor qilish' tugmasini bosing)", 
        reply_markup=cancel_kb()
    )


@router.callback_query(F.data.regexp(r"^up_ep:\d+$"))
async def up_ep_cb(cb: CallbackQuery, state: FSMContext):
    anime_id = int(cb.data.split(":")[1])
    await state.update_data(anime_id=anime_id)
    await state.set_state(UploadEpState.ep_number)
    await cb.answer()
    await cb.message.answer(
        "📝 Qaysi qismini yuklamoqchisiz? Raqamini yuboring (masalan: 12):\n(Amalni to'xtatish uchun '❌ Bekor qilish' ni bosing)", 
        reply_markup=cancel_kb()
    )


@router.message(UploadEpState.ep_number, F.text)
async def upload_ep_number(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    if not msg.text.isdigit():
        await msg.answer("❗ Qism raqami faqat butun son bo'lishi kerak. Iltimos raqam kiriting:")
        return

    ep_num = int(msg.text)
    data = await state.get_data()
    anime_id = data.get("anime_id")

    existing = await get_episode(anime_id, ep_num)
    if existing:
        await msg.answer(f"❗ Bu animeda {ep_num}-qism allaqachon mavjud!\nBoshqa raqam kiriting yoki avval eski qismni o'chiring.", reply_markup=cancel_kb())
        return

    await state.update_data(ep_number=ep_num)
    await state.set_state(UploadEpState.upload_video)
    await msg.answer(f"📤 {ep_num}-qism uchun video/fayl yuboring:", reply_markup=cancel_kb())


@router.message(UploadEpState.upload_video, F.video | F.document)
async def receive_video(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    anime_id = data.get("anime_id")
    ep_number = data.get("ep_number", 1)
    anime = await get_anime_by_id(anime_id)
    if not anime:
        await msg.answer("❌ Anime topilmadi", reply_markup=admin_kb())
        return

    # Accept both video and document
    if msg.video:
        file_id = msg.video.file_id
        file_unique_id = msg.video.file_unique_id
        duration = msg.video.duration or 0
    elif msg.document:
        file_id = msg.document.file_id
        file_unique_id = msg.document.file_unique_id
        duration = 0
    else:
        await msg.answer("❗ Faqat video yoki document yuboring.", reply_markup=admin_kb())
        return

    await add_episode({
        "anime_id": anime_id,
        "ep_number": ep_number,
        "title": f"{ep_number}-qism",
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "message_id": 0,
        "duration": duration,
        "quality": "default",
        "subtitles": "none",
        "added_by": msg.from_user.id,
    })

    title = html.escape(anime.get("title_en") or "Anime")
    genres = html.escape(anime.get("genres") or "-")
    kind = (anime.get("status") or "SERIAL").upper()
    cover = anime.get("cover_image") or ""

    # Adminga faqat rasmli javob (talab bo'yicha)
    if cover:
        await msg.answer_photo(
            photo=cover,
            caption=(
                f"✅ Yuklandi\n"
                f"🆔 Anime ID: <code>{anime_id}</code>\n"
                f"🎌 {title}\n"
                f"🎭 {genres}\n"
                f"📁 {kind}\n"
                f"📺 Qism: {ep_number}"
            ),
            parse_mode="HTML",
            reply_markup=admin_kb(),
        )
    else:
        await msg.answer(
            f"✅ Yuklandi\nAnime ID: {anime_id}\nQism: {ep_number}",
            reply_markup=admin_kb(),
        )

    # Ulangan kanallarga xabar yuborish
    channels = await get_publish_channels()
    if not channels:
        await msg.answer("ℹ️ Ulangan kanal yo'q. '📡 Kanallar' orqali qo'shing.")
    else:
        me = await msg.bot.get_me()
        deep_link = f"https://t.me/{me.username}?start=anime_{anime_id}"

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton

        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="▷ Tomosha qilish ◁", url=deep_link))

        caption = (
            f"🎌 <b>{title}</b>\n"
            f"📺 <b>{ep_number}-qism yuklandi</b>\n\n"
            f"🎭 Janr: {genres}\n"
            f"📁 Turi: {kind}\n\n"
            "👇 Botda tomosha qilish uchun tugmani bosing"
        )

        sent_ok, sent_fail = 0, 0
        for ch in channels:
            try:
                ch_raw = str(ch["channel_id"]).strip()
                ch_id = int(ch_raw) if ch_raw.lstrip("-").isdigit() else ch_raw
                if cover:
                    await msg.bot.send_photo(
                        chat_id=ch_id,
                        photo=cover,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=b.as_markup()
                    )
                else:
                    await msg.bot.send_message(
                        chat_id=ch_id,
                        text=caption,
                        parse_mode="HTML",
                        reply_markup=b.as_markup()
                    )
                sent_ok += 1
            except Exception as e:
                import logging
                logging.error(f"Kanalga yuborishda xato ({ch['channel_id']}): {e}")
                sent_fail += 1

        await msg.answer(f"📡 Kanallarga yuborildi: ✅ {sent_ok} | ❌ {sent_fail}")

    await log_action(msg.from_user.id, "upload_ep", f"{anime_id}:{ep_number}")


# ===================== Kanal boshqaruvi =====================
@router.message(F.text == "📡 Kanallar")
@router.callback_query(F.data == "admin_channels")
async def channels_panel(event):
    if not await is_admin(event.from_user.id):
        return

    channels = await get_publish_channels()
    lines = ["📡 <b>Kanal boshqaruvi (CRUD)</b>"]
    if channels:
        for item in channels[:30]:
            title = item.get("title") or "-"
            required = "✅" if int(item.get("is_required", 1) or 0) else "❌"
            lines.append(f"• <code>{item['channel_id']}</code> — {title} | Majburiy: {required}")
    else:
        lines.append("(bo'sh)")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel"))
    b.row(InlineKeyboardButton(text="✏️ Kanalni tahrirlash", callback_data="edit_channel"))
    b.row(InlineKeyboardButton(text="🔁 Majburiy ON/OFF", callback_data="toggle_channel_required"))
    b.row(InlineKeyboardButton(text="➖ Kanal o'chirish", callback_data="remove_channel"))

    text = "\n".join(lines)
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await event.answer()
        await event.message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "add_channel")
async def add_channel_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    await state.set_state(ChannelState.add_channel)
    await cb.answer()
    await cb.message.answer(
        "📡 <b>Kanal qo'shish</b>\n\n"
        "1️⃣ Kanaldan biror xabar forward qiling\n"
        "   (Bot avtomatik aniqlaydi)\n\n"
        "2️⃣ Yoki qo'lda yozing:\n"
        "   <code>-1001234567890|Kanal nomi|https://t.me/kanal</code>\n\n"
        "Eslatma: yangi kanal avtomatik majburiy obuna kanaliga qo'shiladi.",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(ChannelState.add_channel, F.text)
async def add_channel_finish(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    raw = msg.text.strip()
    parts = raw.split("|")
    channel_id = parts[0].strip() if len(parts) > 0 else ""
    title = parts[1].strip() if len(parts) > 1 else "Kanal"
    join_link = parts[2].strip() if len(parts) > 2 else ""

    if not channel_id:
        await msg.answer("❗ Kanal ID kiriting")
        return

    await add_publish_channel(channel_id, title, msg.from_user.id, join_link=join_link, is_required=1)
    await state.clear()
    await msg.answer("✅ Kanal qo'shildi", reply_markup=admin_kb())


@router.message(ChannelState.add_channel, F.forward_from_chat)
async def add_channel_forward(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    channel = msg.forward_from_chat
    if channel.type not in ("channel", "supergroup"):
        await msg.answer("❗ Faqat kanal yoki guruh forward qiling")
        return

    channel_id = str(channel.id)
    title = channel.title or "Kanal"
    join_link = f"https://t.me/{channel.username}" if channel.username else ""

    # Botning adminligini tekshirish
    try:
        member = await msg.bot.get_chat_member(channel.id, msg.bot.id)
        if member.status not in ("administrator", "creator"):
            await msg.answer("⚠️ Bot bu kanalda admin emas!")
            return
    except Exception as e:
        await msg.answer(f"❌ Xato: {e}")
        return

    await add_publish_channel(channel_id, title, msg.from_user.id, join_link=join_link, is_required=1)
    await state.clear()
    await msg.answer(f"✅ Kanal qo'shildi: {title}\nID: <code>{channel_id}</code>", parse_mode="HTML", reply_markup=admin_kb())


@router.callback_query(F.data == "edit_channel")
async def edit_channel_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    await state.set_state(ChannelState.edit_channel)
    await cb.answer()
    await cb.message.answer(
        "✏️ <b>Kanalni tahrirlash</b>\n\n"
        "Format:\n"
        "<code>-1001234567890|Yangi nom|https://t.me/yangi_link</code>\n\n"
        "Linkni o'chirish uchun 3-qismni bo'sh qoldiring.",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(ChannelState.edit_channel, F.text)
async def edit_channel_finish(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    parts = msg.text.strip().split("|")
    if len(parts) < 2:
        await msg.answer("❗ Format: <code>id|nom|link</code>", parse_mode="HTML")
        return

    channel_id = parts[0].strip()
    title = parts[1].strip()
    join_link = parts[2].strip() if len(parts) > 2 else ""

    channel = await get_publish_channel(channel_id)
    if not channel:
        await msg.answer("❌ Bunday kanal topilmadi")
        return

    await update_publish_channel(channel_id, title=title or channel.get("title", "Kanal"), join_link=join_link)
    await state.clear()
    await msg.answer("✅ Kanal tahrirlandi", reply_markup=admin_kb())


@router.callback_query(F.data == "toggle_channel_required")
async def toggle_channel_required_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    await state.set_state(ChannelState.toggle_required)
    await cb.answer()
    await cb.message.answer(
        "🔁 <b>Majburiy obuna ON/OFF</b>\n\n"
        "Kanal ID yuboring.\n"
        "Masalan: <code>-1001234567890</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(ChannelState.toggle_required, F.text)
async def toggle_channel_required_finish(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    channel_id = msg.text.strip()
    channel = await get_publish_channel(channel_id)
    if not channel:
        await msg.answer("❌ Bunday kanal topilmadi")
        return

    new_value = 0 if int(channel.get("is_required", 1) or 0) else 1
    await update_publish_channel(channel_id, is_required=new_value)
    await state.clear()
    status = "yoqildi ✅" if new_value else "o'chirildi ❌"
    await msg.answer(f"✅ Majburiy obuna {status}", reply_markup=admin_kb())


@router.callback_query(F.data == "remove_channel")
async def remove_channel_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    await state.set_state(ChannelState.remove_channel)
    await cb.answer()
    await cb.message.answer("O'chiriladigan kanal ID ni yuboring:", reply_markup=cancel_kb())


@router.message(ChannelState.remove_channel, F.text)
async def remove_channel_finish(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    channel_id = msg.text.strip()
    await remove_publish_channel(channel_id)
    await state.clear()
    await msg.answer("✅ Kanal o'chirildi", reply_markup=admin_kb())


# ===================== Root admin management =====================
@router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(cb: CallbackQuery):
    if not is_root_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    delegated = await list_delegated_admins()
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="admin_add_user"))
    b.row(InlineKeyboardButton(text="➖ Adminni olib tashlash", callback_data="admin_remove_user"))

    text = f"👥 Delegat adminlar: <b>{len(delegated)}</b>"
    await cb.answer()
    await cb.message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "admin_add_user")
async def admin_add_user_start(cb: CallbackQuery, state: FSMContext):
    if not is_root_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    await state.set_state(AdminManageState.waiting_add)
    await cb.answer()
    await cb.message.answer("Admin bo'ladigan user ID yuboring:", reply_markup=cancel_kb())


@router.message(AdminManageState.waiting_add, F.text)
async def admin_add_user_finish(msg: Message, state: FSMContext):
    if not is_root_admin(msg.from_user.id):
        await state.clear()
        return

    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    if not msg.text.strip().isdigit():
        await msg.answer("❗ Faqat raqam")
        return

    uid = int(msg.text.strip())
    if is_root_admin(uid):
        await state.clear()
        await msg.answer("ℹ️ Bu foydalanuvchi root admin")
        return

    await add_delegated_admin(uid, msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ {uid} admin qilindi", reply_markup=admin_kb())


@router.callback_query(F.data == "admin_remove_user")
async def admin_remove_user_start(cb: CallbackQuery, state: FSMContext):
    if not is_root_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    await state.set_state(AdminManageState.waiting_remove)
    await cb.answer()
    await cb.message.answer("Adminlikdan olinadigan user ID yuboring:", reply_markup=cancel_kb())


@router.message(AdminManageState.waiting_remove, F.text)
async def admin_remove_user_finish(msg: Message, state: FSMContext):
    if not is_root_admin(msg.from_user.id):
        await state.clear()
        return

    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    if not msg.text.strip().isdigit():
        await msg.answer("❗ Faqat raqam")
        return

    uid = int(msg.text.strip())
    if is_root_admin(uid):
        await state.clear()
        await msg.answer("❌ Root adminni o'chirib bo'lmaydi")
        return

    await remove_delegated_admin(uid)
    await state.clear()
    await msg.answer(f"✅ {uid} adminlikdan olindi", reply_markup=admin_kb())


# ===================== Epizod / anime boshqaruvi =====================
@router.callback_query(F.data.regexp(r"^manage_eps:\d+$"))
async def manage_eps(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    episodes = await get_episodes(anime_id)
    anime = await get_anime_by_id(anime_id)
    title = (anime or {}).get("title_en", "Anime")

    await cb.answer()
    if not episodes:
        await cb.message.answer(f"📺 {title}: epizod yo'q")
        return

    await cb.message.answer(
        f"📋 {title} epizodlari ({len(episodes)})",
        reply_markup=admin_ep_list_kb(episodes, anime_id),
    )


@router.callback_query(F.data.regexp(r"^del_ep:\d+:\d+$"))
async def del_ep_confirm(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return

    _, anime_id, ep_num = cb.data.split(":")
    await delete_episode(int(anime_id), int(ep_num))
    await cb.answer(f"✅ {ep_num}-qism o'chirildi")


# ===================== Anime ro'yxati va boshqaruvi =====================
@router.callback_query(F.data.regexp(r"^admin_anime_list(?::\d+)?$"))
async def admin_anime_list(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    page = 1
    if ":" in cb.data:
        page = int(cb.data.split(":")[1])

    items = await get_all_anime(page=page, per_page=10, include_inactive=True)
    total = await get_total_anime_count(include_inactive=True)
    total_pages = max(1, (total + 10 - 1) // 10)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    for a in items:
        t = a.get("title_en") or a.get("title_jp") or "?"
        t = (t[:35] + "...") if len(t) > 35 else t
        ep_count = a.get("total_ep", 0)
        status = "🟢" if int(a.get("is_active", 1) or 0) else "🔴"
        b.row(InlineKeyboardButton(text=f"{status} {t} ({ep_count} ep)", callback_data=f"admin_anime_detail:{a['id']}"))

    # Sahifalash
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin_anime_list:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin_anime_list:{page+1}"))
    if nav:
        b.row(*nav)

    await cb.answer()
    await cb.message.answer(
        f"📋 <b>Anime ro'yxati</b> — {total} ta\n\nAnime tanlang:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data.regexp(r"^admin_anime_detail:\d+$"))
async def admin_anime_detail(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)

    if not anime:
        await cb.answer("❌ Anime topilmadi", show_alert=True)
        return

    episodes = await get_episodes(anime_id)
    ep_count = len(episodes)

    title = anime.get("title_en") or anime.get("title_jp") or "?"
    genres = anime.get("genres") or "N/A"
    status = anime.get("status") or "N/A"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Nomi", callback_data=f"edit_anime_title:{anime_id}"))
    b.row(InlineKeyboardButton(text="🎭 Janr", callback_data=f"edit_anime_genres:{anime_id}"))
    b.row(InlineKeyboardButton(text="📁 Turi (MOVIE/SERIAL)", callback_data=f"edit_anime_status:{anime_id}"))
    b.row(InlineKeyboardButton(text="🖼 Rasm", callback_data=f"edit_anime_cover:{anime_id}"))
    b.row(InlineKeyboardButton(text="📤 Epizod yuklash", callback_data=f"upload_ep_for:{anime_id}"))
    b.row(InlineKeyboardButton(text="📋 Epizodlar", callback_data=f"manage_eps:{anime_id}"))
    if int(anime.get("is_active", 1) or 0):
        b.row(InlineKeyboardButton(text="🗑 Animeni o'chirish", callback_data=f"del_anime:{anime_id}"))
    else:
        b.row(InlineKeyboardButton(text="♻️ Qayta tiklash", callback_data=f"restore_anime:{anime_id}"))
    b.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_anime_list"))

    text = (
        f"🎌 <b>{title}</b>\n\n"
        f"🆔 ID: <code>{anime_id}</code>\n"
        f"🎭 Janr: {genres}\n"
        f"📁 Status: {status}\n"
        f"🔘 Holat: {'Aktiv' if int(anime.get('is_active', 1) or 0) else 'Noaktiv'}\n"
        f"📺 Epizodlar: <b>{ep_count}</b> ta\n"
    )

    cover = anime.get("cover_image")

    await cb.answer()
    if cover:
        await cb.message.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^upload_ep_for:\d+$"))
async def upload_ep_for_anime(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)

    if not anime:
        await cb.answer("❌ Anime topilmadi", show_alert=True)
        return

    await state.update_data(anime_id=anime_id)
    await state.set_state(UploadEpState.ep_number)
    await cb.answer()
    await cb.message.answer("Epizod raqamini yuboring:", reply_markup=cancel_kb())


@router.callback_query(F.data.regexp(r"^del_anime:\d+$"))
async def del_anime_confirm(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"confirm_del_anime:{anime_id}"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="admin_anime_list")
    )

    title = anime.get("title_en") or anime.get("title_jp") or "?"
    await cb.answer()
    await cb.message.answer(
        f"⚠️ <b>Ishonchingiz komilmi?</b>\n\n"
        f"🎌 {title}\n"
        f"🆔 ID: {anime_id}\n\n"
        f"Bu anime va barcha epizodlari o'chiriladi!",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data.regexp(r"^confirm_del_anime:\d+$"))
async def del_anime_execute(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)
    title = anime.get("title_en") or anime.get("title_jp") or "?" if anime else "Anime"

    await delete_anime(anime_id)
    await cb.answer(f"✅ {title} o'chirildi", show_alert=True)
    await cb.message.delete()

    # Anime ro'yxatiga qaytish
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    items = await get_all_anime(page=1, per_page=10, include_inactive=True)
    total = await get_total_anime_count(include_inactive=True)

    b = InlineKeyboardBuilder()
    for a in items:
        t = a.get("title_en") or a.get("title_jp") or "?"
        b.row(InlineKeyboardButton(text=f"🎌 {t}", callback_data=f"admin_anime_detail:{a['id']}"))

    if total > 10:
        b.row(InlineKeyboardButton(text="➡️ Keyingi", callback_data="admin_anime_list:2"))

    await cb.message.answer(
        f"📋 <b>Anime ro'yxati</b> — {total} ta\n\nAnime tanlang:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data.regexp(r"^restore_anime:\d+$"))
async def restore_anime_execute(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    await set_anime_active(anime_id, 1)
    await cb.answer("✅ Anime qayta tiklandi")
    await admin_anime_detail(cb)


@router.callback_query(F.data.regexp(r"^edit_anime_title:\d+$"))
async def edit_anime_title_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return
    anime_id = int(cb.data.split(":")[1])
    await state.set_state(EditAnimeState.title)
    await state.update_data(anime_id=anime_id)
    await cb.answer()
    await cb.message.answer("Yangi anime nomini yuboring:", reply_markup=cancel_kb())


@router.message(EditAnimeState.title, F.text)
async def edit_anime_title_finish(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return
    data = await state.get_data()
    anime_id = int(data.get("anime_id"))
    await update_anime_fields(anime_id, title_en=msg.text.strip())
    await state.clear()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Anime panelga qaytish", callback_data=f"admin_anime_detail:{anime_id}"))
    await msg.answer("✅ Nom yangilandi", reply_markup=admin_kb())
    await msg.answer("👇 Anime panelga qaytish:", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^edit_anime_genres:\d+$"))
async def edit_anime_genres_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return
    anime_id = int(cb.data.split(":")[1])
    await state.set_state(EditAnimeState.genres)
    await state.update_data(anime_id=anime_id)
    await cb.answer()
    await cb.message.answer("Yangi janrni yuboring (vergul bilan):", reply_markup=cancel_kb())


@router.message(EditAnimeState.genres, F.text)
async def edit_anime_genres_finish(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return
    data = await state.get_data()
    anime_id = int(data.get("anime_id"))
    await update_anime_fields(anime_id, genres=msg.text.strip())
    await state.clear()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Anime panelga qaytish", callback_data=f"admin_anime_detail:{anime_id}"))
    await msg.answer("✅ Janr yangilandi", reply_markup=admin_kb())
    await msg.answer("👇 Anime panelga qaytish:", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^edit_anime_status:\d+$"))
async def edit_anime_status_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return
    anime_id = int(cb.data.split(":")[1])
    await state.set_state(EditAnimeState.status)
    await state.update_data(anime_id=anime_id)
    await cb.answer()
    await cb.message.answer("Turi yuboring: MOVIE yoki SERIAL", reply_markup=cancel_kb())


@router.message(EditAnimeState.status, F.text)
async def edit_anime_status_finish(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    status = msg.text.strip().upper()
    if status not in {"MOVIE", "SERIAL"}:
        await msg.answer("❗ Faqat MOVIE yoki SERIAL")
        return

    data = await state.get_data()
    anime_id = int(data.get("anime_id"))
    await update_anime_fields(anime_id, status=status)
    await state.clear()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Anime panelga qaytish", callback_data=f"admin_anime_detail:{anime_id}"))
    await msg.answer("✅ Tur yangilandi", reply_markup=admin_kb())
    await msg.answer("👇 Anime panelga qaytish:", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^edit_anime_cover:\d+$"))
async def edit_anime_cover_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return
    anime_id = int(cb.data.split(":")[1])
    await state.set_state(EditAnimeState.cover)
    await state.update_data(anime_id=anime_id)
    await cb.answer()
    await cb.message.answer("Yangi rasm yuboring:", reply_markup=cancel_kb())


@router.message(EditAnimeState.cover, F.photo)
async def edit_anime_cover_finish(msg: Message, state: FSMContext):
    data = await state.get_data()
    anime_id = int(data.get("anime_id"))
    await update_anime_fields(anime_id, cover_image=msg.photo[-1].file_id)
    await state.clear()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Anime panelga qaytish", callback_data=f"admin_anime_detail:{anime_id}"))
    await msg.answer("✅ Rasm yangilandi", reply_markup=admin_kb())
    await msg.answer("👇 Anime panelga qaytish:", reply_markup=b.as_markup())


@router.message(EditAnimeState.cover, F.text)
async def edit_anime_cover_text(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return
    await msg.answer("❗ Rasm yuboring yoki bekor qiling")


# ===================== Majburiy obuna sozlamalari =====================
@router.callback_query(F.data == "admin_subscribe_settings")
async def subscribe_settings_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    await channels_panel(cb)


# ===================== Anime qo'shish (start) =====================
@router.message(F.text == "➕ Anime qo'shish")
async def add_anime_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id):
        return

    await state.set_state(AddAnimeState.title)
    await msg.answer("🌟 Anime nomini yozing (inglizcha):", reply_markup=cancel_kb())


@router.message(AddAnimeState.title, F.text)
async def add_anime_title(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    await state.update_data(title=msg.text.strip())
    await state.set_state(AddAnimeState.genres)
    await msg.answer("🎭 Janr yozing (vergul bilan):\nMisol: Action, Adventure, Fantasy")


@router.message(AddAnimeState.genres, F.text)
async def add_anime_genres(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    await state.update_data(genres=msg.text.strip())

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🎥 Film (MOVIE)", callback_data="anime_kind:MOVIE"),
        InlineKeyboardButton(text="📺 Serial", callback_data="anime_kind:SERIAL"),
    )
    await msg.answer("📁 Turini tanlang:", reply_markup=b.as_markup())


# ===================== Admin panel (statistika) =====================
@router.message(F.text == "📊 Admin panel")
async def admin_panel(msg: Message):
    if not await is_admin(msg.from_user.id):
        return

    stats = await get_stats()

    text = (
        "📊 <b>Admin panel</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{stats['total_users']}</b>\n"
        f"📅 Bugungi faollar: <b>{stats['today_users']}</b>\n"
        f"🌟 Animalar: <b>{stats['total_anime']}</b>\n"
        f"📺 Epizodlar: <b>{stats['total_episodes']}</b>\n"
        f"👁 Ko'rishlar: <b>{stats['total_views']}</b>\n"
        f"❤️ Sevimlilar: <b>{stats['total_favorites']}</b>\n"
        f"⭐ Reytinglar: <b>{stats['total_ratings']}</b>\n"
        f"💬 Izohlar: <b>{stats['total_comments']}</b>\n"
    )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📋 Anime ro'yxati", callback_data="admin_anime_list"))
    b.row(InlineKeyboardButton(text="📤 Epizod yuklash", callback_data="admin_upload_ep"))
    b.row(InlineKeyboardButton(text="📡 Kanallar", callback_data="admin_channels"))
    b.row(InlineKeyboardButton(text="💬 Tasdiqlanmagan izohlar", callback_data="admin_pending_comments"))
    if is_root_admin(msg.from_user.id):
        b.row(InlineKeyboardButton(text="👑 Admin boshqaruvi", callback_data="admin_manage_admins"))

    await msg.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


# ===================== Izoh tasdiqlash / o'chirish =====================
@router.callback_query(F.data == "admin_pending_comments")
async def admin_pending_comments_list(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    comments = await get_pending_comments()
    await cb.answer()

    if not comments:
        await cb.message.answer("✅ Tasdiqlanmagan izoh yo'q")
        return

    from utils.keyboards import admin_comment_kb
    for c in comments[:10]:
        name = c.get("first_name") or "Anonim"
        title = c.get("title_en") or "Anime"
        text = (
            f"💬 <b>Izoh tasdiqlash</b>\n\n"
            f"🌟 Anime: {html.escape(title)}\n"
            f"👤 {html.escape(name)}\n\n"
            f"📝 {html.escape(c['text'][:300])}"
        )
        await cb.message.answer(text, parse_mode="HTML", reply_markup=admin_comment_kb(c["id"]))


@router.callback_query(F.data.regexp(r"^approve_comment:\d+$"))
async def approve_comment_handler(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    comment_id = int(cb.data.split(":")[1])
    await approve_comment(comment_id)
    await cb.answer("✅ Izoh tasdiqlandi", show_alert=True)
    try:
        await cb.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.regexp(r"^delete_comment:\d+$"))
async def delete_comment_handler(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    comment_id = int(cb.data.split(":")[1])
    # Bazadan o'chiramiz
    import aiosqlite
    from config import DATABASE_PATH
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM comments WHERE id=?", (comment_id,))
        await db.commit()

    await cb.answer("🗑 Izoh o'chirildi", show_alert=True)
    try:
        await cb.message.delete()
    except Exception:
        pass
