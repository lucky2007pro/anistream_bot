from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from database.db import is_admin as db_is_admin


def main_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="🎬 Barcha animalar"))
    b.row(KeyboardButton(text="🔥 Trending"),  KeyboardButton(text="🏆 Top anime"))
    b.row(KeyboardButton(text="🌸 Mavsumiy"),  KeyboardButton(text="🎲 Tasodifiy"))
    b.row(KeyboardButton(text="❤️ Sevimlilar"),KeyboardButton(text="📜 Tarixim"))
    b.row(KeyboardButton(text="👤 Profilim"),  KeyboardButton(text="🆘 Yordam"))
    b.row(KeyboardButton(text="🔽 Menyuni yopish"))
    return b.as_markup(resize_keyboard=True)


def admin_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="🎬 Barcha animalar"))
    b.row(KeyboardButton(text="🔥 Trending"),  KeyboardButton(text="🏆 Top anime"))
    b.row(KeyboardButton(text="➕ Anime qo'shish"), KeyboardButton(text="📤 Epizod yuklash"))
    b.row(KeyboardButton(text="❤️ Sevimlilar"),KeyboardButton(text="📜 Tarixim"))
    b.row(KeyboardButton(text="👤 Profilim"),  KeyboardButton(text="💬 Izohlar"))
    b.row(KeyboardButton(text="📊 Admin panel"),KeyboardButton(text="📢 Broadcast"))
    b.row(KeyboardButton(text="⚙️ Sozlamalar"))
    b.row(KeyboardButton(text="🔽 Menyuni yopish"))
    return b.as_markup(resize_keyboard=True)


def reopen_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="☰ Menyuni ochish"))
    return b.as_markup(resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="❌ Bekor qilish"))
    return b.as_markup(resize_keyboard=True)


async def get_main_kb(user_id: int):
    return admin_kb() if await db_is_admin(user_id) else main_kb()


def subscribe_kb(subscribe_channel: str = "") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if subscribe_channel:
        b.row(InlineKeyboardButton(text="📢 Kanalga o'tish",
                                   url=f"https://t.me/{subscribe_channel.lstrip('@')}"))
    b.row(InlineKeyboardButton(text="✅ Obuna bo'ldim, tekshirish",
                               callback_data="check_subscribe"))
    return b.as_markup()


def anime_card_kb(anime_id: int, is_fav: bool, is_sub: bool,
                  ep_count: int = 0, user_rating: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    # Epizodlar tugmasi faqat epizod bo'lsagina
    if ep_count > 0:
        b.row(InlineKeyboardButton(
            text=f"📺 Epizodlar ({ep_count} ta)",
            callback_data=f"eps:{anime_id}:1"
        ))
    # Sevimlilar
    fav_t = "💔 Sev'lilardan chiqarish" if is_fav else "❤️ Sev'lilarga qo'shish"
    fav_cb = f"fav:rm:{anime_id}" if is_fav else f"fav:add:{anime_id}"
    b.row(InlineKeyboardButton(text=fav_t, callback_data=fav_cb))
    # Bildirishnoma obunasi
    sub_t = "🔕 Bildirishnomani o'chirish" if is_sub else "🔔 Yangi epizod xabari"
    sub_cb = f"sub:off:{anime_id}" if is_sub else f"sub:on:{anime_id}"
    b.row(InlineKeyboardButton(text=sub_t, callback_data=sub_cb))
    # Reyting
    rating_t = f"⭐ Reytingim: {user_rating}/10" if user_rating else "⭐ Reyting berish"
    b.row(InlineKeyboardButton(text=rating_t, callback_data=f"rate:{anime_id}"))
    # Izohlar
    b.row(
        InlineKeyboardButton(text="💬 Izohlar", callback_data=f"cmts:{anime_id}"),
        InlineKeyboardButton(text="🌐 AniList", url=f"https://anilist.co/anime/{anime_id}"),
    )
    return b.as_markup()


def episodes_kb(episodes: list, page: int, per_page: int, anime_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    start = (page - 1) * per_page
    page_eps = episodes[start: start + per_page]
    total_pages = max(1, (len(episodes) + per_page - 1) // per_page)
    # Episode tugmalari 4 ta qator
    row = []
    for ep in page_eps:
        ep_num = ep["ep_number"]
        quality = ep.get("quality","")
        q_icon = "🎬" if "1080" in quality else "📺" if "720" in quality else "▶️"
        row.append(InlineKeyboardButton(
            text=f"{q_icon}{ep_num}",
            callback_data=f"ep:{anime_id}:{ep_num}"
        ))
        if len(row) == 4:
            b.row(*row); row = []
    if row: b.row(*row)
    # Navigatsiya
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"eps:{anime_id}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"eps:{anime_id}:{page+1}"))
    b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 Animega qaytish", callback_data=f"local_anime:{anime_id}"))
    return b.as_markup()


def episode_watch_kb(anime_id: int, ep_num: int, total_eps: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    nav = []
    if ep_num > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"ep:{anime_id}:{ep_num-1}"))
    if ep_num < total_eps:
        nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"ep:{anime_id}:{ep_num+1}"))
    if nav: b.row(*nav)
    b.row(InlineKeyboardButton(text="📋 Barcha epizodlar", callback_data=f"eps:{anime_id}:1"))
    b.row(InlineKeyboardButton(text="🔙 Anime", callback_data=f"local_anime:{anime_id}"))
    return b.as_markup()


def rating_kb(anime_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    stars = ["1⭐","2⭐","3⭐","4⭐","5⭐","6⭐","7⭐","8⭐","9⭐","10⭐"]
    row = []
    for i, s in enumerate(stars, 1):
        row.append(InlineKeyboardButton(text=s, callback_data=f"do_rate:{anime_id}:{i}"))
        if len(row) == 5: b.row(*row); row = []
    if row: b.row(*row)
    b.row(InlineKeyboardButton(text="❌ Bekor", callback_data=f"local_anime:{anime_id}"))
    return b.as_markup()


def search_results_kb(results, page, total_pages, query) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in results:
        t = a.get("title",{}).get("english") or a.get("title",{}).get("romaji") or "?"
        t = (t[:35]+"…") if len(t)>35 else t
        b.row(InlineKeyboardButton(text=f"🎌 {t}", callback_data=f"anilist:{a['id']}"))
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"srch:{query}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄{page}/{total_pages}", callback_data="noop"))
    if page < total_pages: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"srch:{query}:{page+1}"))
    if nav: b.row(*nav)
    return b.as_markup()


def local_anime_list_kb(items: list, page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in items:
        t = a.get("title_en") or a.get("title_jp") or "?"
        t = (t[:33]+"…") if len(t)>33 else t
        ep = a.get("total_ep",0)
        b.row(InlineKeyboardButton(
            text=f"🎌 {t} ({ep}ep)",
            callback_data=f"local_anime:{a['id']}"
        ))
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages: nav.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}:{page+1}"))
    b.row(*nav)
    return b.as_markup()


def admin_anime_kb(anime_id: int, anilist_id: int = 0) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📤 Epizod yuklash", callback_data=f"upload_ep:{anime_id}"))
    b.row(InlineKeyboardButton(text="📋 Epizodlar boshqaruvi", callback_data=f"manage_eps:{anime_id}"))
    b.row(InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_anime:{anime_id}"))
    b.row(InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_anime:{anime_id}"))
    if anilist_id:
        b.row(InlineKeyboardButton(text="🌐 AniList", url=f"https://anilist.co/anime/{anilist_id}"))
    b.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_panel"))
    return b.as_markup()


def admin_ep_list_kb(episodes: list, anime_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for ep in episodes:
        b.row(InlineKeyboardButton(
            text=f"▶️{ep['ep_number']} — {ep.get('quality','?')} | 👁{ep.get('views',0)}",
            callback_data=f"del_ep:{anime_id}:{ep['ep_number']}"
        ))
    b.row(InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"admin_anime:{anime_id}"))
    return b.as_markup()


def favorites_kb(favs: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for a in favs:
        t = a.get("title_en") or a.get("title_jp") or "?"
        t = (t[:30]+"…") if len(t)>30 else t
        b.row(
            InlineKeyboardButton(text=f"🎌 {t}", callback_data=f"local_anime:{a['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"fav:rm:{a['id']}"),
        )
    return b.as_markup()


def comments_kb(comments: list, anime_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✍️ Izoh yozish", callback_data=f"write_comment:{anime_id}"))
    b.row(InlineKeyboardButton(text="🔙 Animega qaytish", callback_data=f"local_anime:{anime_id}"))
    return b.as_markup()


def admin_comment_kb(comment_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_comment:{comment_id}"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"delete_comment:{comment_id}"),
    )
    return b.as_markup()


def back_kb(cb="main") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Orqaga", callback_data=cb)
    return b.as_markup()
