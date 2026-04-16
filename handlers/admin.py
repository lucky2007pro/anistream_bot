"""
Admin panel — anime qo'shish, epizod yuklash, broadcast, izohlar
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Video
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from api.anilist import get_details, search_anime, format_list_item
from database.db import (
    add_anime, get_anime_by_id, delete_anime,
    add_episode, get_episodes, delete_episode,
    get_all_users, get_stats, get_pending_comments,
    approve_comment, get_anime_subscribers, log_action,
    is_admin as db_is_admin,
    is_root_admin,
    get_setting,
    set_setting,
    add_delegated_admin,
    remove_delegated_admin,
    list_delegated_admins,
)
from utils.keyboards import (
    admin_kb, cancel_kb, admin_anime_kb, admin_ep_list_kb,
    admin_comment_kb,
)

router = Router()


async def is_admin(uid: int) -> bool:
    return await db_is_admin(uid)


# ── FSM States ─────────────────────────────────────────────────
class AddAnimeState(StatesGroup):
    search      = State()
    confirm     = State()

class UploadEpState(StatesGroup):
    select_anime = State()
    ep_number    = State()
    ep_quality   = State()
    ep_subtitles = State()
    upload_video = State()

class BroadcastState(StatesGroup):
    writing = State()

class EditAnimeState(StatesGroup):
    field = State()
    value = State()


class SettingsState(StatesGroup):
    waiting_value = State()


class AdminManageState(StatesGroup):
    waiting_add = State()
    waiting_remove = State()


# ═══════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "📊 Admin panel")
async def admin_panel(msg: Message):
    if not await is_admin(msg.from_user.id):
        return
    s = await get_stats()
    text = (
        "📊 <b>Admin Panel</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['total_users']}</b>\n"
        f"🟢 Bugun faol: <b>{s['today_users']}</b>\n"
        f"🎌 Animalar: <b>{s['total_anime']}</b>\n"
        f"📺 Epizodlar: <b>{s['total_episodes']}</b>\n"
        f"👁 Jami ko'rishlar: <b>{s['total_views']}</b>\n"
        f"❤️ Sevimlilar: <b>{s['total_favorites']}</b>\n"
        f"⭐ Reytinglar: <b>{s['total_ratings']}</b>\n"
        f"💬 Izohlar: <b>{s['total_comments']}</b>\n\n"
        "Quyidagi buyruqlardan foydalaning:"
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Anime qo'shish", callback_data="admin_add_anime"),
        InlineKeyboardButton(text="📤 Epizod yuklash", callback_data="admin_upload_ep"),
    )
    b.row(
        InlineKeyboardButton(text="💬 Izohlar", callback_data="admin_comments"),
        InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast"),
    )
    b.row(InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="admin_settings"))
    if is_root_admin(msg.from_user.id):
        b.row(InlineKeyboardButton(text="👥 Adminlar", callback_data="admin_manage_admins"))
    await msg.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.message(F.text == "⚙️ Sozlamalar")
@router.callback_query(F.data == "admin_settings")
async def admin_settings(event):
    uid = event.from_user.id
    if not await is_admin(uid):
        return

    storage_channel = await get_setting("storage_channel", "")
    subscribe_channel = await get_setting("subscribe_channel", "")
    subscribe_channel_id = await get_setting("subscribe_channel_id", "")
    not_set = "o'rnatilmagan"

    text = (
        "⚙️ <b>Bot sozlamalari</b>\n\n"
        f"📦 STORAGE_CHANNEL: <code>{storage_channel or not_set}</code>\n"
        f"📢 SUBSCRIBE_CHANNEL: <code>{subscribe_channel or not_set}</code>\n"
        f"🆔 SUBSCRIBE_CHANNEL_ID: <code>{subscribe_channel_id or not_set}</code>\n\n"
        "Qaysi qiymatni o'zgartirmoqchisiz?"
    )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📦 Storage kanal", callback_data="set_cfg:storage_channel"))
    b.row(InlineKeyboardButton(text="📢 Obuna kanal username", callback_data="set_cfg:subscribe_channel"))
    b.row(InlineKeyboardButton(text="🆔 Obuna kanal ID", callback_data="set_cfg:subscribe_channel_id"))

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await event.answer()
        await event.message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^set_cfg:(storage_channel|subscribe_channel|subscribe_channel_id)$"))
async def set_config_prompt(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id):
        return

    key = cb.data.split(":", 1)[1]
    await state.set_state(SettingsState.waiting_value)
    await state.update_data(setting_key=key)
    await cb.answer()

    hints = {
        "storage_channel": "Misol: -1001234567890",
        "subscribe_channel": "Misol: @my_channel",
        "subscribe_channel_id": "Misol: -1001234567890",
    }
    await cb.message.answer(
        f"Yangi qiymatni yuboring.\n{hints.get(key, '')}\n\n"
        "Qiymatni tozalash uchun: <code>none</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(SettingsState.waiting_value, F.text)
async def set_config_value(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id):
        await state.clear()
        return

    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    data = await state.get_data()
    key = data.get("setting_key")
    value = msg.text.strip()
    if value.lower() in {"none", "null", "-"}:
        value = ""

    await set_setting(key, value)
    await state.clear()
    await msg.answer("✅ Sozlama saqlandi", reply_markup=admin_kb())


@router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(cb: CallbackQuery):
    if not is_root_admin(cb.from_user.id):
        await cb.answer("❌ Sizda bu bo'limga ruxsat yo'q", show_alert=True)
        return

    await cb.answer()
    delegated = await list_delegated_admins()
    text = (
        "👥 <b>Admin boshqaruvi (faqat root admin)</b>\n\n"
        f"Delegat adminlar soni: <b>{len(delegated)}</b>\n\n"
        "• Qo'shish\n"
        "• Olib tashlash\n"
        "• Ro'yxat"
    )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="admin_add_user"))
    b.row(InlineKeyboardButton(text="➖ Adminni olib tashlash", callback_data="admin_remove_user"))
    b.row(InlineKeyboardButton(text="📋 Adminlar ro'yxati", callback_data="admin_list_users"))
    await cb.message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "admin_add_user")
async def admin_add_user_start(cb: CallbackQuery, state: FSMContext):
    if not is_root_admin(cb.from_user.id):
        await cb.answer("❌ Sizda bu amalga ruxsat yo'q", show_alert=True)
        return

    await state.set_state(AdminManageState.waiting_add)
    await cb.answer()
    await cb.message.answer(
        "Yangi admin user ID yuboring:\n"
        "Misol: <code>123456789</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


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
        await msg.answer("❗ Iltimos, faqat raqamli user ID yuboring")
        return

    target_id = int(msg.text.strip())
    if is_root_admin(target_id):
        await state.clear()
        await msg.answer("ℹ️ Bu user allaqachon root admin", reply_markup=admin_kb())
        return

    await add_delegated_admin(target_id, msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ <code>{target_id}</code> admin qilindi", parse_mode="HTML", reply_markup=admin_kb())


@router.callback_query(F.data == "admin_remove_user")
async def admin_remove_user_start(cb: CallbackQuery, state: FSMContext):
    if not is_root_admin(cb.from_user.id):
        await cb.answer("❌ Sizda bu amalga ruxsat yo'q", show_alert=True)
        return

    await state.set_state(AdminManageState.waiting_remove)
    await cb.answer()
    await cb.message.answer(
        "Adminlikdan olinadigan user ID yuboring:\n"
        "Misol: <code>123456789</code>",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


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
        await msg.answer("❗ Iltimos, faqat raqamli user ID yuboring")
        return

    target_id = int(msg.text.strip())
    if is_root_admin(target_id):
        await state.clear()
        await msg.answer("❌ Root adminni olib tashlab bo'lmaydi", reply_markup=admin_kb())
        return

    await remove_delegated_admin(target_id)
    await state.clear()
    await msg.answer(f"✅ <code>{target_id}</code> adminlikdan olindi", parse_mode="HTML", reply_markup=admin_kb())


@router.callback_query(F.data == "admin_list_users")
async def admin_list_users(cb: CallbackQuery):
    if not is_root_admin(cb.from_user.id):
        await cb.answer("❌ Sizda bu bo'limga ruxsat yo'q", show_alert=True)
        return

    delegated = await list_delegated_admins()
    await cb.answer()
    if not delegated:
        await cb.message.answer("📋 Delegat adminlar ro'yxati bo'sh")
        return

    lines = ["📋 <b>Delegat adminlar</b>"]
    for item in delegated[:50]:
        lines.append(f"• <code>{item['user_id']}</code> (added_by: {item.get('added_by', 0)})")
    await cb.message.answer("\n".join(lines), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
#  ANIME QO'SHISH
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "➕ Anime qo'shish")
@router.callback_query(F.data == "admin_add_anime")
async def add_anime_start(event, state: FSMContext):
    uid = event.from_user.id
    if not await is_admin(uid):
        return
    await state.set_state(AddAnimeState.search)
    text = (
        "➕ <b>Anime qo'shish</b>\n\n"
        "AniList ID yoki anime nomini kiriting:\n\n"
        "• ID: <code>21</code> (anilist.co/anime/<b>21</b>)\n"
        "• Nom: <code>Naruto</code>"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=cancel_kb())
    else:
        await event.answer()
        await event.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb())


@router.message(AddAnimeState.search, F.text)
async def add_anime_search(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    query = msg.text.strip()

    # ID bo'lsa to'g'ridan qo'shish
    if query.isdigit():
        anime_id = int(query)
        await state.update_data(anilist_id=anime_id)
        await _show_anime_confirm(msg, state, anime_id)
        return

    # Nom bo'lsa qidirish
    wait = await msg.answer("🔍 Qidirilmoqda...")
    result = await search_anime(query, page=1, per_page=5)
    await wait.delete()

    if not result or not result.get("media"):
        await msg.answer("😔 Topilmadi. Qayta urinib ko'ring:")
        return

    media = result["media"]
    await state.update_data(search_results=[a["id"] for a in media])

    text = f"🔍 <b>'{query}'</b> natijalari:\n\n"
    for i, a in enumerate(media, 1):
        text += format_list_item(a, i) + "\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    for a in media:
        from api.anilist import get_title
        t = get_title(a)
        t = (t[:33]+"…") if len(t)>33 else t
        b.row(InlineKeyboardButton(text=f"✅ {t}", callback_data=f"admin_select:{a['id']}"))
    b.row(InlineKeyboardButton(text="❌ Bekor", callback_data="admin_cancel_state"))

    cover = (media[0].get("coverImage") or {}).get("large","")
    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=b.as_markup())

    await state.set_state(AddAnimeState.confirm)


async def _show_anime_confirm(msg, state, anilist_id):
    anime = await get_details(anilist_id)
    if not anime:
        await msg.answer("❌ Bu ID bo'yicha anime topilmadi!")
        return

    from api.anilist import format_card
    text = f"📋 <b>Tasdiqlash:</b>\n\n{format_card(anime)}"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Qo'shish", callback_data=f"admin_confirm:{anilist_id}"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="admin_cancel_state"),
    )
    cover = (anime.get("coverImage") or {}).get("large","")
    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=b.as_markup())
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=b.as_markup())
    await state.set_state(AddAnimeState.confirm)


@router.callback_query(F.data.regexp(r"^admin_select:\d+$"))
async def admin_select(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    anilist_id = int(cb.data.split(":")[1])
    await state.update_data(anilist_id=anilist_id)
    await _show_anime_confirm(cb.message, state, anilist_id)


@router.callback_query(F.data.regexp(r"^admin_confirm:\d+$"))
async def admin_confirm_add(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    anilist_id = int(cb.data.split(":")[1])

    anime = await get_details(anilist_id)
    if not anime:
        await cb.answer("❌ Topilmadi", show_alert=True)
        return

    import re
    def clean(t): return re.sub(r"<[^>]+>","",t or "")

    data = {
        "anilist_id":   anilist_id,
        "title_en":     anime.get("title",{}).get("english",""),
        "title_jp":     anime.get("title",{}).get("romaji",""),
        "title_uz":     "",
        "description":  clean(anime.get("description","")),
        "cover_image":  (anime.get("coverImage") or {}).get("extraLarge","") or (anime.get("coverImage") or {}).get("large",""),
        "banner_image": anime.get("bannerImage","") or "",
        "genres":       ", ".join(anime.get("genres",[])[:6]),
        "status":       anime.get("status",""),
        "total_ep":     anime.get("episodes") or 0,
        "year":         anime.get("seasonYear"),
        "season":       anime.get("season",""),
        "score":        (anime.get("averageScore") or 0) / 10,
        "added_by":     cb.from_user.id,
    }
    local_id = await add_anime(data)
    title = data["title_en"] or data["title_jp"]

    await cb.message.answer(
        f"✅ <b>{title}</b> qo'shildi!\n\n"
        f"🆔 Lokal ID: <code>{local_id}</code>\n"
        f"📤 Endi epizodlar yuklashingiz mumkin.",
        parse_mode="HTML",
        reply_markup=admin_anime_kb(local_id, anilist_id),
    )


@router.callback_query(F.data == "admin_cancel_state")
async def cancel_state(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer("❌ Bekor qilindi")
    await cb.message.answer("❌ Bekor qilindi", reply_markup=admin_kb())


# ═══════════════════════════════════════════════════════════════
#  EPIZOD YUKLASH
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "📤 Epizod yuklash")
@router.callback_query(F.data == "admin_upload_ep")
async def upload_ep_start(event, state: FSMContext):
    uid = event.from_user.id
    if not await is_admin(uid):
        return
    await state.set_state(UploadEpState.select_anime)
    text = (
        "📤 <b>Epizod yuklash</b>\n\n"
        "Anime nomini yoki lokal ID ni kiriting:\n"
        "<i>Misol: Naruto yoki 1</i>"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=cancel_kb())
    else:
        await event.answer()
        await event.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb())


@router.message(UploadEpState.select_anime, F.text)
async def upload_select_anime(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return

    query = msg.text.strip()
    from database.db import get_anime_by_id, search_local_anime

    if query.isdigit():
        anime = await get_anime_by_id(int(query))
        if anime:
            await state.update_data(anime_id=anime["id"])
            title = anime.get("title_en") or anime.get("title_jp")
            await state.set_state(UploadEpState.ep_number)
            await msg.answer(
                f"✅ <b>{title}</b>\n\nNecha-epizod raqamini kiriting:\n<i>Misol: 1</i>",
                parse_mode="HTML",
            )
            return

    results = await search_local_anime(query)
    if not results:
        await msg.answer("❌ Botda bunday anime yo'q. Avval anime qo'shing: ➕ Anime qo'shish")
        return

    if len(results) == 1:
        await state.update_data(anime_id=results[0]["id"])
        title = results[0].get("title_en") or results[0].get("title_jp")
        await state.set_state(UploadEpState.ep_number)
        await msg.answer(
            f"✅ <b>{title}</b>\n\nEpizod raqamini kiriting:",
            parse_mode="HTML",
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    for a in results[:5]:
        t = a.get("title_en") or a.get("title_jp") or "?"
        b.row(InlineKeyboardButton(text=t, callback_data=f"sel_anime_ep:{a['id']}"))
    await msg.answer("Qaysi animega epizod qo'shmoqchisiz?", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^sel_anime_ep:\d+$"))
async def sel_anime_ep(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)
    await state.update_data(anime_id=anime_id)
    await state.set_state(UploadEpState.ep_number)
    title = anime.get("title_en") or anime.get("title_jp") if anime else "?"
    await cb.message.answer(
        f"✅ <b>{title}</b>\n\nEpizod raqamini kiriting:\n<i>Misol: 1</i>",
        parse_mode="HTML",
    )


@router.message(UploadEpState.ep_number, F.text)
async def upload_ep_number(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear(); await msg.answer("❌ Bekor", reply_markup=admin_kb()); return
    if not msg.text.isdigit():
        await msg.answer("❗ Raqam kiriting"); return
    await state.update_data(ep_number=int(msg.text))
    await state.set_state(UploadEpState.ep_quality)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    for q in ["360p","480p","720p","1080p"]:
        b.row(InlineKeyboardButton(text=q, callback_data=f"set_quality:{q}"))
    await msg.answer("🎬 Sifatni tanlang:", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^set_quality:.+$"))
async def set_quality(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    quality = cb.data.split(":")[1]
    await state.update_data(quality=quality)
    await state.set_state(UploadEpState.ep_subtitles)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    for s in [("O'zbek","uz"),("Rus","ru"),("Ingliz","en"),("Yo'q","none")]:
        b.row(InlineKeyboardButton(text=s[0], callback_data=f"set_subs:{s[1]}"))
    await cb.message.answer("📝 Subtitle tilini tanlang:", reply_markup=b.as_markup())


@router.callback_query(F.data.regexp(r"^set_subs:.+$"))
async def set_subs(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    subs = cb.data.split(":")[1]
    await state.update_data(subtitles=subs)
    await state.set_state(UploadEpState.upload_video)

    data = await state.get_data()
    anime = await get_anime_by_id(data["anime_id"])
    title = anime.get("title_en") or anime.get("title_jp") if anime else "?"

    await cb.message.answer(
        f"📤 <b>Video yuklash</b>\n\n"
        f"🎌 Anime: <b>{title}</b>\n"
        f"📺 Epizod: <b>{data['ep_number']}</b>\n"
        f"🎬 Sifat: <b>{data['quality']}</b>\n\n"
        f"Endi video faylni yuboring:",
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )


@router.message(UploadEpState.upload_video, F.video)
async def receive_video(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    video: Video = msg.video
    status_msg = await msg.answer("⏳ Video saqlanmoqda...")

    # Kanalga yuborish (storage)
    storage_channel = await get_setting("storage_channel", "")
    channel_msg_id = 0
    if storage_channel:
        try:
            sent = await msg.bot.copy_message(
                chat_id=int(storage_channel) if storage_channel.lstrip("-").isdigit() else storage_channel,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id,
            )
            channel_msg_id = sent.message_id
        except Exception as e:
            await msg.answer(f"⚠️ Kanalga yuborishda xato: {e}\nLokal saqlanadi.")

    ep_data = {
        "anime_id":      data["anime_id"],
        "ep_number":     data["ep_number"],
        "file_id":       video.file_id,
        "file_unique_id":video.file_unique_id,
        "message_id":    channel_msg_id,
        "duration":      video.duration or 0,
        "quality":       data.get("quality","480p"),
        "subtitles":     data.get("subtitles","none"),
        "added_by":      msg.from_user.id,
    }
    await add_episode(ep_data)

    anime = await get_anime_by_id(data["anime_id"])
    title = anime.get("title_en") or anime.get("title_jp") if anime else "?"

    await status_msg.delete()
    await msg.answer(
        f"✅ <b>{title}</b> — {data['ep_number']}-epizod yuklandi!\n\n"
        f"🎬 Sifat: {data.get('quality')}\n"
        f"📝 Subtitle: {data.get('subtitles')}\n"
        f"📦 Kanal: {'✅' if channel_msg_id else '❌'}",
        parse_mode="HTML",
        reply_markup=admin_kb(),
    )

    # Obunachilarga xabar berish
    subscribers = await get_anime_subscribers(data["anime_id"])
    if subscribers:
        notif_text = (
            f"🔔 <b>Yangi epizod!</b>\n\n"
            f"🎌 <b>{title}</b>\n"
            f"📺 {data['ep_number']}-epizod qo'shildi!\n"
            f"🎬 Sifat: {data.get('quality')}"
        )
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(
            text=f"▶️ Ko'rish",
            callback_data=f"ep:{data['anime_id']}:{data['ep_number']}"
        ))
        ok, fail = 0, 0
        for uid in subscribers:
            try:
                await msg.bot.send_message(uid, notif_text, parse_mode="HTML", reply_markup=b.as_markup())
                ok += 1
            except Exception:
                fail += 1
        await msg.answer(f"🔔 Bildirishnoma: {ok} ta obunachiga yuborildi")

    await log_action(msg.from_user.id, "upload_ep", f"{data['anime_id']}:{data['ep_number']}")


# ═══════════════════════════════════════════════════════════════
#  EPIZOD BOSHQARUVI
# ═══════════════════════════════════════════════════════════════
@router.callback_query(F.data.regexp(r"^manage_eps:\d+$"))
async def manage_eps(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return
    await cb.answer()
    anime_id = int(cb.data.split(":")[1])
    episodes = await get_episodes(anime_id)
    anime = await get_anime_by_id(anime_id)
    title = anime.get("title_en") or anime.get("title_jp") if anime else "?"

    if not episodes:
        await cb.message.answer(f"📺 <b>{title}</b>\n\nHali epizod yo'q.", parse_mode="HTML")
        return

    text = f"📋 <b>{title}</b> — {len(episodes)} ta epizod\n\n🗑 O'chirish uchun bosing:"
    kb = admin_ep_list_kb(episodes, anime_id)
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.regexp(r"^del_ep:\d+:\d+$"))
async def del_ep_confirm(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return
    _, anime_id, ep_num = cb.data.split(":")
    await delete_episode(int(anime_id), int(ep_num))
    await cb.answer(f"✅ {ep_num}-epizod o'chirildi!")
    await manage_eps(cb)


@router.callback_query(F.data.regexp(r"^admin_anime:\d+$"))
async def admin_anime_detail(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return
    await cb.answer()
    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)
    if not anime:
        await cb.answer("❌ Topilmadi", show_alert=True); return
    title = anime.get("title_en") or anime.get("title_jp") or "?"
    ep_count = anime.get("total_ep",0)
    text = (
        f"🎌 <b>{title}</b>\n"
        f"📺 Epizodlar: <b>{ep_count}</b>\n"
        f"📅 {anime.get('season','')} {anime.get('year','')}\n"
        f"✅ Status: {anime.get('status','')}"
    )
    kb = admin_anime_kb(anime_id, anime.get("anilist_id",0))
    cover = anime.get("cover_image","")
    if cover:
        await cb.message.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.regexp(r"^del_anime:\d+$"))
async def del_anime(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return
    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)
    title = anime.get("title_en") or anime.get("title_jp") if anime else "?"
    await delete_anime(anime_id)
    await cb.answer(f"✅ {title} o'chirildi!")
    await cb.message.answer(f"🗑 <b>{title}</b> o'chirildi.", parse_mode="HTML", reply_markup=admin_kb())


# ═══════════════════════════════════════════════════════════════
#  IZOHLARNI TASDIQLASH
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "💬 Izohlar")
@router.callback_query(F.data == "admin_comments")
async def admin_comments(event):
    uid = event.from_user.id
    if not await is_admin(uid):
        return
    comments = await get_pending_comments()
    if not comments:
        text = "💬 Hozircha tasdiqlanmagan izoh yo'q ✅"
        if isinstance(event, Message):
            await event.answer(text)
        else:
            await event.answer()
            await event.message.answer(text)
        return

    text = f"💬 <b>Tasdiqlanmagan izohlar:</b> {len(comments)} ta\n\n"
    if isinstance(event, CallbackQuery): await event.answer()
    msg = event if isinstance(event, Message) else event.message

    for c in comments[:5]:
        name = c.get("first_name","?")
        anime_t = c.get("title_en","?")
        await msg.answer(
            f"👤 <b>{name}</b>\n🎌 {anime_t}\n\n💬 {c['text'][:300]}",
            parse_mode="HTML",
            reply_markup=admin_comment_kb(c["id"]),
        )


@router.callback_query(F.data.regexp(r"^approve_comment:\d+$"))
async def do_approve_comment(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return
    cid = int(cb.data.split(":")[1])
    await approve_comment(cid)
    await cb.answer("✅ Izoh tasdiqlandi!")
    try: await cb.message.delete()
    except Exception: pass


@router.callback_query(F.data.regexp(r"^delete_comment:\d+$"))
async def do_delete_comment(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id):
        return
    await cb.answer("🗑 O'chirildi")
    try: await cb.message.delete()
    except Exception: pass


# ═══════════════════════════════════════════════════════════════
#  BROADCAST
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "📢 Broadcast")
@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(event, state: FSMContext):
    uid = event.from_user.id
    if not await is_admin(uid):
        return
    await state.set_state(BroadcastState.writing)
    text = (
        "📢 <b>Broadcast</b>\n\n"
        "Barcha foydalanuvchilarga yuboriladigan xabarni yozing.\n"
        "HTML format ishlaydi: &lt;b&gt;, &lt;i&gt;, &lt;a href&gt;"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=cancel_kb())
    else:
        await event.answer()
        await event.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb())


@router.message(BroadcastState.writing, F.text)
async def do_broadcast(msg: Message, state: FSMContext):
    if msg.text == "❌ Bekor qilish":
        await state.clear()
        await msg.answer("❌ Bekor", reply_markup=admin_kb())
        return
    await state.clear()
    users = await get_all_users()
    ok, fail = 0, 0
    status = await msg.answer(f"⏳ Yuborilmoqda... 0/{len(users)}", reply_markup=admin_kb())
    for i, uid in enumerate(users):
        try:
            await msg.bot.send_message(uid, msg.text, parse_mode="HTML")
            ok += 1
        except Exception:
            fail += 1
        if (i+1) % 30 == 0:
            try:
                await status.edit_text(f"⏳ {i+1}/{len(users)}")
            except Exception:
                pass
    await status.edit_text(f"✅ Broadcast yakunlandi!\n📤 Yuborildi: {ok}\n❌ Xato: {fail}")
