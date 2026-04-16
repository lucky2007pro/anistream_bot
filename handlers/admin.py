"""
Soddalashtirilgan admin panel:
- Anime qo'shish (nom, janr, turi, rasm)
- Epizod yuklash
- Ulangan kanallarni boshqarish
- Root admin: delegat admin qo'shish/o'chirish
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Video
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import (
    add_anime, get_anime_by_id, delete_anime,
    add_episode, get_episodes, delete_episode,
    get_stats, log_action, search_local_anime,
    is_admin as db_is_admin, is_root_admin,
    add_delegated_admin, remove_delegated_admin, list_delegated_admins,
    add_publish_channel, remove_publish_channel, get_publish_channels,
    get_setting, set_setting,
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
    remove_channel = State()


class AdminManageState(StatesGroup):
    waiting_add = State()
    waiting_remove = State()


class SubscribeSettingState(StatesGroup):
    waiting_channel = State()


@router.message(F.text == "📊 Admin panel")
async def admin_panel(msg: Message):
    if not await is_admin(msg.from_user.id):
        return

    s = await get_stats()
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Anime qo'shish", callback_data="admin_add_anime"),
        InlineKeyboardButton(text="📤 Epizod yuklash", callback_data="admin_upload_ep"),
    )
    b.row(InlineKeyboardButton(text="📡 Kanallar", callback_data="admin_channels"))
    b.row(InlineKeyboardButton(text="🔐 Majburiy obuna", callback_data="admin_subscribe_settings"))
    if is_root_admin(msg.from_user.id):
        b.row(InlineKeyboardButton(text="👥 Adminlar", callback_data="admin_manage_admins"))

    text = (
        "📊 <b>Admin Panel</b>\n\n"
        f"👥 Foydalanuvchi: <b>{s['total_users']}</b>\n"
        f"🎌 Anime: <b>{s['total_anime']}</b>\n"
        f"📺 Epizod: <b>{s['total_episodes']}</b>\n"
        f"👁 Ko'rishlar: <b>{s['total_views']}</b>"
    )
    await msg.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


# ===================== Anime qo'shish =====================
@router.message(F.text == "➕ Anime qo'shish")
@router.callback_query(F.data == "admin_add_anime")
async def add_anime_start(event, state: FSMContext):
    if not await is_admin(event.from_user.id):
        return

    await state.set_state(AddAnimeState.title)
    text = "Anime nomini yuboring:"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=cancel_kb())
    else:
        await event.answer()
        await event.message.answer(text, reply_markup=cancel_kb())


@router.message(AddAnimeState.title, F.text)
async def add_anime_title(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    await state.update_data(title=msg.text.strip())
    await state.set_state(AddAnimeState.genres)
    await msg.answer("Janrlarni yozing (vergul bilan):\nMisol: Romantika, Komediya")


@router.message(AddAnimeState.genres, F.text)
async def add_anime_genres(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    await state.update_data(genres=msg.text.strip())
    await state.set_state(AddAnimeState.kind)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🎬 Film", callback_data="anime_kind:MOVIE"),
        InlineKeyboardButton(text="📺 Serial", callback_data="anime_kind:SERIAL"),
    )
    await msg.answer("Anime turini tanlang:", reply_markup=b.as_markup())


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
@router.message(F.text == "📤 Epizod yuklash")
@router.callback_query(F.data == "admin_upload_ep")
async def upload_ep_start(event, state: FSMContext):
    if not await is_admin(event.from_user.id):
        return

    await state.set_state(UploadEpState.select_anime)
    text = "Anime ID yoki nomini yozing:"
    if isinstance(event, Message):
        await event.answer(text, reply_markup=cancel_kb())
    else:
        await event.answer()
        await event.message.answer(text, reply_markup=cancel_kb())


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
    else:
        results = await search_local_anime(query)
        if len(results) == 1:
            anime = results[0]
        elif len(results) > 1:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            b = InlineKeyboardBuilder()
            for a in results[:8]:
                t = a.get("title_en") or "?"
                b.row(InlineKeyboardButton(text=f"{t} (ID:{a['id']})", callback_data=f"sel_anime_ep:{a['id']}"))
            await msg.answer("Qaysi anime?", reply_markup=b.as_markup())
            return

    if not anime:
        await msg.answer("❌ Anime topilmadi")
        return

    await state.update_data(anime_id=anime["id"])

    if (anime.get("status") or "").upper() == "MOVIE":
        await state.update_data(ep_number=1)
        await state.set_state(UploadEpState.upload_video)
        await msg.answer("🎬 Film uchun video yuboring:", reply_markup=cancel_kb())
        return

    await state.set_state(UploadEpState.ep_number)
    await msg.answer("Epizod raqamini yuboring: (masalan 1)")


@router.callback_query(F.data.regexp(r"^sel_anime_ep:\d+$"))
async def sel_anime_ep(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)
    await cb.answer()

    await state.update_data(anime_id=anime_id)
    if (anime or {}).get("status", "").upper() == "MOVIE":
        await state.update_data(ep_number=1)
        await state.set_state(UploadEpState.upload_video)
        await cb.message.answer("🎬 Film uchun video yuboring:", reply_markup=cancel_kb())
    else:
        await state.set_state(UploadEpState.ep_number)
        await cb.message.answer("Epizod raqamini yuboring:")


@router.message(UploadEpState.ep_number, F.text)
async def upload_ep_number(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    if not msg.text.isdigit():
        await msg.answer("❗ Raqam kiriting")
        return

    await state.update_data(ep_number=int(msg.text))
    await state.set_state(UploadEpState.upload_video)
    await msg.answer("📤 Video yuboring:", reply_markup=cancel_kb())


@router.message(UploadEpState.upload_video, F.video)
async def receive_video(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    anime_id = data.get("anime_id")
    ep_number = data.get("ep_number", 1)
    anime = await get_anime_by_id(anime_id)
    if not anime:
        await msg.answer("❌ Anime topilmadi", reply_markup=admin_kb())
        return

    video: Video = msg.video
    await add_episode({
        "anime_id": anime_id,
        "ep_number": ep_number,
        "title": f"{ep_number}-qism",
        "file_id": video.file_id,
        "file_unique_id": video.file_unique_id,
        "message_id": 0,
        "duration": video.duration or 0,
        "quality": "default",
        "subtitles": "none",
        "added_by": msg.from_user.id,
    })

    title = anime.get("title_en") or "Anime"
    genres = anime.get("genres") or "-"
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

    # Ulangan kanallarga rasm yuborish
    channels = await get_publish_channels()
    if not channels:
        await msg.answer("ℹ️ Ulangan kanal yo'q. '📡 Kanallar' orqali qo'shing.")
    elif not cover:
        await msg.answer("⚠️ Anime rasmi yo'q, kanallarga e'lon yuborilmadi.")
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
                channel_id = ch["channel_id"]
                await msg.bot.send_photo(
                    chat_id=channel_id,
                    photo=cover,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=b.as_markup()
                )
                sent_ok += 1
            except Exception:
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
    lines = ["📡 <b>Ulangan kanallar</b>"]
    if channels:
        for item in channels[:30]:
            title = item.get("title") or "-"
            lines.append(f"• <code>{item['channel_id']}</code> — {title}")
    else:
        lines.append("(bo'sh)")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel"))
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
        "   <code>-1001234567890|Kanal nomi</code>",
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
    channel_id, title = (raw.split("|", 1) + [""])[:2]
    channel_id = channel_id.strip()
    title = title.strip() or "Kanal"

    if not channel_id:
        await msg.answer("❗ Kanal ID kiriting")
        return

    await add_publish_channel(channel_id, title, msg.from_user.id)
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

    # Botning adminligini tekshirish
    try:
        member = await msg.bot.get_chat_member(channel.id, msg.bot.id)
        if member.status not in ("administrator", "creator"):
            await msg.answer("⚠️ Bot bu kanalda admin emas!")
            return
    except Exception as e:
        await msg.answer(f"❌ Xato: {e}")
        return

    await add_publish_channel(channel_id, title, msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ Kanal qo'shildi: {title}\nID: <code>{channel_id}</code>", parse_mode="HTML", reply_markup=admin_kb())


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


@router.callback_query(F.data.regexp(r"^del_anime:\d+$"))
async def del_anime(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return

    anime_id = int(cb.data.split(":")[1])
    await delete_anime(anime_id)
    await cb.answer("✅ Anime o'chirildi")


# ===================== Majburiy obuna sozlamalari =====================
@router.callback_query(F.data == "admin_subscribe_settings")
async def subscribe_settings_menu(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    subscribe_channel = await get_setting("subscribe_channel", "")
    subscribe_channel_id = await get_setting("subscribe_channel_id", "")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Kanal o'rnatish", callback_data="set_subscribe_channel"))
    b.row(InlineKeyboardButton(text="🗑 Obunani o'chirish", callback_data="clear_subscribe_channel"))

    status = "✅ Yoqilgan" if subscribe_channel_id else "❌ O'chirilgan"
    text = (
        f"🔐 <b>Majburiy obuna sozlamalari</b>\n\n"
        f"Status: {status}\n"
        f"Kanal: {subscribe_channel or 'Belgilanmagan'}\n"
        f"Kanal ID: <code>{subscribe_channel_id or 'Yo\'q'}</code>\n\n"
        f"📌 Majburiy obuna yoqish uchun:\n"
        f"1. <b>✏️ Kanal o'rnatish</b> tugmasini bosing\n"
        f"2. Kanaldan biror xabar forward qiling yoki\n"
        f"3. <code>@username|channel_id</code> formatida yuboring"
    )

    await cb.answer()
    await cb.message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "set_subscribe_channel")
async def set_subscribe_channel_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    await state.set_state(SubscribeSettingState.waiting_channel)
    await cb.answer()
    await cb.message.answer(
        "📢 <b>Majburiy obuna kanali o'rnatish</b>\n\n"
        "1️⃣ Kanaldan biror xabar forward qiling\n"
        "   (Bot avtomatik aniqlaydi)\n\n"
        "2️⃣ Yoki qo'lda yozing:\n"
        "   <code>@kanalUsername|-1001234567890</code>\n\n"
        "Misol: <code>@anime_uz|-1001234567890</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(SubscribeSettingState.waiting_channel, F.forward_from_chat)
async def set_subscribe_from_forward(msg: Message, state: FSMContext):
    channel = msg.forward_from_chat
    if channel.type not in ("channel", "supergroup"):
        await msg.answer("❗ Faqat kanal yoki guruh forward qiling")
        return

    channel_id = str(channel.id)
    channel_username = f"@{channel.username}" if channel.username else channel.title or "Kanal"

    # Botning adminligini tekshirish
    try:
        member = await msg.bot.get_chat_member(channel.id, msg.bot.id)
        if member.status not in ("administrator", "creator"):
            await msg.answer("⚠️ Bot bu kanalda admin emas! Botni kanalga admin qilib qo'shing.")
            return
    except Exception as e:
        await msg.answer(f"❌ Xato: {e}")
        return

    await set_setting("subscribe_channel", channel_username)
    await set_setting("subscribe_channel_id", channel_id)
    await state.clear()

    await msg.answer(
        f"✅ <b>Majburiy obuna yoqildi!</b>\n\n"
        f"📢 Kanal: {channel_username}\n"
        f"🆔 ID: <code>{channel_id}</code>\n\n"
        f"Endi barcha foydalanuvchilar bu kanalga obuna bo'lishi shart.",
        parse_mode="HTML",
        reply_markup=admin_kb(),
    )


@router.message(SubscribeSettingState.waiting_channel, F.text)
async def set_subscribe_manual(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor qilindi", reply_markup=admin_kb())
        return

    raw = msg.text.strip()
    if "|" not in raw:
        await msg.answer("❗ Format: <code>@username|channel_id</code>", parse_mode="HTML")
        return

    channel_username, channel_id = raw.split("|", 1)
    channel_username = channel_username.strip()
    channel_id = channel_id.strip()

    if not channel_username or not channel_id:
        await msg.answer("❗ Ikkala qiymat ham kerak: username va ID")
        return

    # ID formatini tekshirish
    if not (channel_id.lstrip("-").isdigit() or channel_id.startswith("@")):
        await msg.answer("❗ Kanal ID raqam bo'lishi kerak, masalan: -1001234567890")
        return

    await set_setting("subscribe_channel", channel_username)
    await set_setting("subscribe_channel_id", channel_id)
    await state.clear()

    await msg.answer(
        f"✅ <b>Majburiy obuna yoqildi!</b>\n\n"
        f"📢 Kanal: {channel_username}\n"
        f"🆔 ID: <code>{channel_id}</code>\n\n"
        f"⚠️ Agar bot kanalda admin bo'lmasa, uni admin qilib qo'shing!",
        parse_mode="HTML",
        reply_markup=admin_kb(),
    )


@router.callback_query(F.data == "clear_subscribe_channel")
async def clear_subscribe_channel(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        await cb.answer("❌ Ruxsat yo'q", show_alert=True)
        return

    await set_setting("subscribe_channel", "")
    await set_setting("subscribe_channel_id", "")

    await cb.answer("✅ Majburiy obuna o'chirildi", show_alert=True)
    await cb.message.answer(
        "✅ <b>Majburiy obuna o'chirildi</b>\n\n"
        "Endi foydalanuvchilar kanalga obuna bo'lmasdan ham botdan foydalanishlari mumkin.",
        parse_mode="HTML",
    )
