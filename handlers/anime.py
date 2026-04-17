"""
Anime ko'rish, epizodlar, reyting, izoh, sevimlilar, bildirishnoma
"""
import html as html_mod
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import (
    get_anime_by_id, get_anime_by_anilist, get_episodes, get_episode,
    add_favorite, remove_favorite, is_favorite, get_favorites,
    subscribe_anime, unsubscribe_anime, is_subscribed_anime,
    set_rating, get_anime_rating, get_user_rating,
    add_comment, get_comments, get_history, get_last_watched,
    add_history, increment_views, get_all_anime, get_most_viewed,
    get_top_anime_local, log_action, get_all_admin_ids, get_total_anime_count
)
from utils.keyboards import (
    anime_card_kb, episodes_kb, episode_watch_kb,
    rating_kb, favorites_kb, comments_kb, back_kb, local_anime_list_kb,
)
from config import EPISODES_PER_PAGE

router = Router()


class CommentState(StatesGroup):
    writing = State()


# ═══════════════════════════════════════════════════════════════
#  LOCAL ANIME KO'RSATISH (bazadagi anime)
# ═══════════════════════════════════════════════════════════════
async def show_local_anime(target, anime_id: int, user_id: int):
    anime = await get_anime_by_id(anime_id)
    if not anime:
        txt = "❌ Anime topilmadi"
        if isinstance(target, CallbackQuery):
            await target.answer(txt, show_alert=True)
        else:
            await target.answer(txt)
        return

    episodes = await get_episodes(anime_id)
    ep_count = len(episodes)
    fav = await is_favorite(user_id, anime_id)
    sub = await is_subscribed_anime(user_id, anime_id)
    u_rating = await get_user_rating(user_id, anime_id)
    avg_rating, votes = await get_anime_rating(anime_id)
    last_watched = await get_last_watched(user_id, anime_id)

    title = html_mod.escape(anime.get("title_en") or anime.get("title_jp") or "?")
    genres = html_mod.escape(anime.get("genres","") or "N/A")
    status_map = {"FINISHED":"✅ Tugagan","RELEASING":"🔄 Chiqmoqda","CANCELLED":"❌ Bekor"}
    status = status_map.get(anime.get("status",""), anime.get("status",""))

    stars = "⭐" * round(avg_rating / 2) if avg_rating else ""
    rating_str = f"⭐ {avg_rating}/10 ({votes} ovoz) {stars}" if votes else "⭐ Hali reyting yo'q"

    text = (
        f"🎌 <b>{title}</b>\n"
        f"<i>{anime.get('title_jp','')}</i>\n\n"
        f"{rating_str}\n"
        f"📺 {ep_count} epizod  |  {status}\n"
        f"🎭 {genres}\n"
        f"📅 {anime.get('season','')} {anime.get('year','')}\n"
    )
    if last_watched:
        text += f"\n▶️ <b>Oxirgi ko'rilgan:</b> {last_watched}-epizod\n"
    if anime.get("description"):
        desc = anime["description"][:400] + "..." if len(anime.get("description","")) > 400 else anime.get("description","")
        text += f"\n📖 {desc}"

    kb = anime_card_kb(anime_id, fav, sub, ep_count, u_rating)
    cover = anime.get("cover_image","")

    await log_action(user_id, "view_anime", str(anime_id))

    if isinstance(target, CallbackQuery):
        # Har doim yangi xabar yuborish (edit qilmaslik)
        if cover:
            await target.message.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            await target.message.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        if cover:
            await target.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.regexp(r"^local_anime:\d+$"))
async def local_anime_cb(cb: CallbackQuery):
    await cb.answer()
    await show_local_anime(cb, int(cb.data.split(":")[1]), cb.from_user.id)


# ═══════════════════════════════════════════════════════════════
#  BARCHA ANIMALAR RO'YXATI
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "🎬 Barcha anime")
@router.message(F.text == "🎬 Barcha animalar")
async def all_anime_cmd(msg: Message):
    items = await get_all_anime(page=1, per_page=20)
    if not items:
        await msg.answer(
            "😔 Hozircha bot bazasida anime yo'q.\n"
            "Admin tez orada qo'shadi! 🎌"
        )
        return

    total_count = await get_total_anime_count()
    total_pages = max(1, (total_count + 20 - 1) // 20)

    text = f"🎬 <b>Botdagi animalar</b> — {total_count} ta\n\n"
    for i, a in enumerate(items, 1):
        t = a.get("title_en") or a.get("title_jp") or "?"
        ep = a.get("total_ep", 0)
        text += f"{i}. <b>{t}</b> ({ep} ep)\n"

    kb = local_anime_list_kb(items, 1, total_pages, "all_anime")

    # Har bir sahifadagi birinchi animening rasmini ko'rsatamiz
    cover = items[0].get("cover_image","") if items else ""
    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.regexp(r"^all_anime:\d+$"))
async def all_anime_page(cb: CallbackQuery):
    await cb.answer()
    page = int(cb.data.split(":")[1])
    items = await get_all_anime(page=page, per_page=20)

    if not items:
        await cb.answer("❌ Bu sahifada anime yo'q", show_alert=True)
        return

    total_count = await get_total_anime_count()
    total_pages = max(1, (total_count + 20 - 1) // 20)

    text = f"🎬 <b>Botdagi animalar</b> — {total_count} ta (Sahifa {page}/{total_pages})\n\n"
    for i, a in enumerate(items, (page-1)*20+1):
        t = a.get("title_en") or a.get("title_jp") or "?"
        ep = a.get("total_ep", 0)
        text += f"{i}. <b>{t}</b> ({ep} ep)\n"

    kb = local_anime_list_kb(items, page, total_pages, "all_anime")

    # Har bir sahifadagi birinchi animening rasmini ko'rsatish
    new_cover = items[0].get("cover_image","") if items else ""

    try:
        # Rasmni edit qilishga harakat qilamiz
        if new_cover and cb.message.photo:
            # Agar oldingi xabarda ham rasm bo'lsa, faqat caption va rasmni edit qilamiz
            from aiogram.types import InputMediaPhoto
            await cb.message.edit_media(
                media=InputMediaPhoto(media=new_cover, caption=text, parse_mode="HTML"),
                reply_markup=kb
            )
        elif cb.message.photo:
            # Rasm bor lekin yangi rasm yo'q - faqat caption edit
            await cb.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            # Oldingi xabarda rasm yo'q edi
            await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        # Agar edit ishlamasa, yangi xabar yuboramiz
        try:
            if new_cover:
                await cb.message.answer_photo(photo=new_cover, caption=text, parse_mode="HTML", reply_markup=kb)
            else:
                await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await cb.answer("❌ Xatolik yuz berdi", show_alert=True)


# ═══════════════════════════════════════════════════════════════
#  EPIZODLAR
# ═══════════════════════════════════════════════════════════════
@router.callback_query(F.data.regexp(r"^eps:\d+:\d+$"))
async def episodes_list(cb: CallbackQuery):
    await cb.answer()
    _, anime_id, page = cb.data.split(":")
    anime_id, page = int(anime_id), int(page)

    anime = await get_anime_by_id(anime_id)
    episodes = await get_episodes(anime_id)

    if not episodes:
        await cb.answer("❌ Epizodlar hali yuklanmagan", show_alert=True)
        return

    title = anime.get("title_en") or anime.get("title_jp") if anime else "Anime"
    total = len(episodes)
    total_pages = max(1, (total + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)

    text = (
        f"📺 <b>{title}</b>\n\n"
        f"📊 Jami: <b>{total}</b> epizod\n"
        f"📄 Sahifa: {page}/{total_pages}\n\n"
        "👇 Epizodni tanlang:"
    )
    kb = episodes_kb(episodes, page, EPISODES_PER_PAGE, anime_id)
    try:
        await cb.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
#  EPIZODNI YUBORISH (kanaldan forward)
# ═══════════════════════════════════════════════════════════════
@router.callback_query(F.data.regexp(r"^ep:\d+:\d+$"))
async def send_episode(cb: CallbackQuery):
    await cb.answer("⏳ Yuklanmoqda...")
    _, anime_id, ep_num = cb.data.split(":")
    anime_id, ep_num = int(anime_id), int(ep_num)

    episode = await get_episode(anime_id, ep_num)
    anime = await get_anime_by_id(anime_id)
    episodes = await get_episodes(anime_id)
    total_eps = len(episodes)

    if not episode or not episode.get("file_id"):
        await cb.message.answer(
            "❌ Bu epizod hali yuklanmagan.\n🔔 Bildirishnomaga obuna bo'ling!"
        )
        return

    title = html_mod.escape((anime.get("title_en") or anime.get("title_jp") or "Anime") if anime else "Anime")
    ep_title = html_mod.escape(episode.get("title","") or f"{ep_num}-epizod")
    quality = episode.get("quality","")
    subs = episode.get("subtitles","none")
    subs_str = "✅ O'zbekcha" if "uz" in subs else "🇷🇺 Ruscha" if "ru" in subs else "🇬🇧 Inglizcha" if "en" in subs else "❌ Yo'q"

    caption = (
        f"🎌 <b>{title}</b>\n"
        f"📺 <b>{ep_title}</b>\n\n"
        f"🎬 Sifat: <b>{quality}</b>\n"
        f"📝 Subtitle: {subs_str}"
    )

    kb = episode_watch_kb(anime_id, ep_num, total_eps)

    # Har doim file_id orqali yuboramiz (storage kanali faqat admin yuklash oqimida ishlatiladi)
    try:
        await cb.message.answer_video(
            video=episode["file_id"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb,
            supports_streaming=True,
        )
    except Exception:
        # Agar video sifatida yuborilmasa, document sifatida yuboramiz
        try:
            await cb.message.answer_document(
                document=episode["file_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception as e2:
            await cb.message.answer(
                f"❌ Video yuborishda xato: {e2}\n\nAdmin bilan bog'laning."
            )
            return

    await increment_views(episode["id"])
    await add_history(cb.from_user.id, anime_id, ep_num)
    await log_action(cb.from_user.id, "watch_ep", f"{anime_id}:{ep_num}")


# ═══════════════════════════════════════════════════════════════
#  SEVIMLILAR
# ═══════════════════════════════════════════════════════════════
@router.callback_query(F.data.regexp(r"^fav:(add|rm):\d+$"))
async def fav_toggle(cb: CallbackQuery):
    parts = cb.data.split(":")
    action, anime_id = parts[1], int(parts[2])
    uid = cb.from_user.id

    if action == "add":
        await add_favorite(uid, anime_id)
        await cb.answer("❤️ Sevimlilarga qo'shildi!")
    else:
        await remove_favorite(uid, anime_id)
        await cb.answer("💔 Sevimlililardan olib tashlandi")

    await show_local_anime(cb, anime_id, uid)


@router.message(F.text == "❤️ Sevimlilar")
async def favorites_cmd(msg: Message):
    favs = await get_favorites(msg.from_user.id)
    if not favs:
        await msg.answer(
            "❤️ <b>Sevimlilar</b>\n\nHozircha bo'sh.\n"
            "Anime kartasidagi ❤️ tugmasini bosing!",
            parse_mode="HTML",
        )
        return
    text = f"❤️ <b>Sevimlilarim</b> — {len(favs)} ta\n\n"
    for a in favs[:15]:
        t = a.get("title_en") or a.get("title_jp") or "?"
        ep = a.get("total_ep",0)
        text += f"• {t} ({ep} ep)\n"
    kb = favorites_kb(favs)
    cover = favs[0].get("cover_image","") if favs else ""
    if cover:
        await msg.answer_photo(photo=cover, caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
#  BILDIRISHNOMA OBUNASI
# ═══════════════════════════════════════════════════════════════
@router.callback_query(F.data.regexp(r"^sub:(on|off):\d+$"))
async def sub_toggle(cb: CallbackQuery):
    parts = cb.data.split(":")
    action, anime_id = parts[1], int(parts[2])
    uid = cb.from_user.id

    if action == "on":
        await subscribe_anime(uid, anime_id)
        await cb.answer("🔔 Yangi epizod chiqqanda xabar olasiz!")
    else:
        await unsubscribe_anime(uid, anime_id)
        await cb.answer("🔕 Bildirishnoma o'chirildi")

    await show_local_anime(cb, anime_id, uid)


# ═══════════════════════════════════════════════════════════════
#  REYTING
# ═══════════════════════════════════════════════════════════════
@router.callback_query(F.data.regexp(r"^rate:\d+$"))
async def rating_cb(cb: CallbackQuery):
    await cb.answer()
    anime_id = int(cb.data.split(":")[1])
    anime = await get_anime_by_id(anime_id)
    title = (anime.get("title_en") or anime.get("title_jp")) if anime else "Anime"
    u_rating = await get_user_rating(cb.from_user.id, anime_id)
    avg, votes = await get_anime_rating(anime_id)

    text = (
        f"⭐ <b>Reyting berish</b>\n\n"
        f"🎌 {title}\n\n"
        f"O'rtacha: <b>{avg}/10</b> ({votes} ovoz)\n"
        f"Sizning reytingiz: <b>{u_rating or 'Berilmagan'}</b>\n\n"
        "Quyidagi tugmalar orqali reyting bering:"
    )
    try:
        await cb.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=rating_kb(anime_id))
    except Exception:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=rating_kb(anime_id))


@router.callback_query(F.data.regexp(r"^do_rate:\d+:\d+$"))
async def do_rate(cb: CallbackQuery):
    _, anime_id, score = cb.data.split(":")
    anime_id, score = int(anime_id), int(score)

    await set_rating(cb.from_user.id, anime_id, score)
    stars = "⭐" * score
    await cb.answer(f"✅ {score}/10 reyting berildi! {stars}", show_alert=True)
    await show_local_anime(cb, anime_id, cb.from_user.id)


# ═══════════════════════════════════════════════════════════════
#  IZOHLAR
# ═══════════════════════════════════════════════════════════════
@router.callback_query(F.data.regexp(r"^cmts:\d+$"))
async def show_comments(cb: CallbackQuery):
    await cb.answer()
    anime_id = int(cb.data.split(":")[1])
    comments = await get_comments(anime_id)
    anime = await get_anime_by_id(anime_id)
    title = (anime.get("title_en") or anime.get("title_jp")) if anime else "Anime"

    if not comments:
        text = f"💬 <b>{title}</b> — Izohlar\n\nHali izoh yo'q. Birinchi bo'ling!"
    else:
        text = f"💬 <b>{title}</b> izohlar ({len(comments)} ta)\n\n"
        for c in comments:
            name = c.get("first_name") or "Anonim"
            text += f"👤 <b>{name}</b>:\n{c['text'][:200]}\n\n"

    kb = comments_kb(comments, anime_id)
    try:
        await cb.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.regexp(r"^write_comment:\d+$"))
async def write_comment_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    anime_id = int(cb.data.split(":")[1])
    await state.set_state(CommentState.writing)
    await state.update_data(anime_id=anime_id)
    await cb.message.answer(
        "✍️ Izohingizni yozing:\n<i>Admin tasdiqlagandan so'ng ko'rinadi</i>",
        parse_mode="HTML",
        reply_markup=__import__("utils.keyboards", fromlist=["cancel_kb"]).cancel_kb(),
    )


@router.message(CommentState.writing, F.text)
async def save_comment(msg: Message, state: FSMContext):
    data = await state.get_data()
    anime_id = data.get("anime_id")
    await state.clear()

    if msg.text == "❌ Bekor qilish":
        from utils.keyboards import get_main_kb
        await msg.answer("❌ Bekor qilindi", reply_markup=await get_main_kb(msg.from_user.id))
        return

    comment_id = await add_comment(msg.from_user.id, anime_id, msg.text[:500])

    # Adminlarga xabar
    anime = await get_anime_by_id(anime_id)
    title = (anime.get("title_en") or anime.get("title_jp")) if anime else "Anime"
    from utils.keyboards import admin_comment_kb
    for admin_id in await get_all_admin_ids():
        try:
            await msg.bot.send_message(
                admin_id,
                f"💬 <b>Yangi izoh tasdiqlash kerak</b>\n\n"
                f"🎌 Anime: {title}\n"
                f"👤 Foydalanuvchi: {msg.from_user.first_name} (@{msg.from_user.username})\n\n"
                f"💬 {msg.text[:300]}",
                parse_mode="HTML",
                reply_markup=admin_comment_kb(comment_id),
            )
        except Exception:
            pass

    from utils.keyboards import get_main_kb
    await msg.answer(
        "✅ Izohingiz yuborildi!\nAdmin tasdiqlagandan so'ng ko'rinadi.",
        reply_markup=await get_main_kb(msg.from_user.id),
    )


# ═══════════════════════════════════════════════════════════════
#  KO'RISH TARIXI
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "📜 Tarixim")
async def history_cmd(msg: Message):
    history = await get_history(msg.from_user.id, 20)
    if not history:
        await msg.answer(
            "📜 <b>Ko'rish tarixi</b>\n\nHali hech narsa ko'rilmagan.",
            parse_mode="HTML",
        )
        return
    text = f"📜 <b>Ko'rish tarixi</b> (so'nggi {len(history)} ta)\n\n"
    for h in history:
        t = h.get("title_en") or h.get("title_jp") or "?"
        ep = h.get("ep_number","?")
        date = h.get("watched_at","")[:10]
        text += f"• <b>{t}</b> — {ep}-epizod <i>({date})</i>\n"
    await msg.answer(text, parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════
#  PROFIL
# ═══════════════════════════════════════════════════════════════
@router.message(F.text == "👤 Profilim")
async def profile_cmd(msg: Message):
    from database.db import get_user, get_favorites, get_history
    from aiogram.utils.deep_linking import create_start_link
    uid = msg.from_user.id
    user = await get_user(uid)
    favs = await get_favorites(uid)
    hist = await get_history(uid, 100)

    ref_link = f"https://t.me/{(await msg.bot.get_me()).username}?start=ref_{uid}"

    text = (
        f"👤 <b>Profilim</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Ism: <b>{msg.from_user.first_name}</b>\n"
        f"📅 Qo'shilgan: <b>{(user or {}).get('joined_at','?')[:10]}</b>\n\n"
        f"❤️ Sevimlilar: <b>{len(favs)}</b> ta anime\n"
        f"📺 Ko'rilgan: <b>{len(hist)}</b> ta epizod\n"
        f"👥 Taklif qildi: <b>{(user or {}).get('ref_count',0)}</b> kishi\n\n"
        f"🔗 <b>Referral havola:</b>\n"
        f"<code>{ref_link}</code>"
    )
    await msg.answer(text, parse_mode="HTML")
