"""
To'liq ma'lumotlar bazasi:
- users, anime_list, episodes, favorites
- watch_history, ratings, comments
- notifications, referrals, stats
"""
from pathlib import Path

import aiosqlite
import logging

from config import DATABASE_PATH, ADMIN_IDS

logger = logging.getLogger(__name__)
DB_PATH = DATABASE_PATH


async def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.executescript("""
            -- Foydalanuvchilar
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                lang          TEXT DEFAULT 'uz',
                is_blocked    INTEGER DEFAULT 0,
                is_premium    INTEGER DEFAULT 0,
                ref_by        INTEGER DEFAULT 0,
                ref_count     INTEGER DEFAULT 0,
                joined_at     TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Admin tomonidan qo'shilgan animalar
            CREATE TABLE IF NOT EXISTS anime_list (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                anilist_id    INTEGER UNIQUE,
                title_uz      TEXT,
                title_en      TEXT,
                title_jp      TEXT,
                description   TEXT,
                cover_image   TEXT,
                banner_image  TEXT,
                genres        TEXT,
                status        TEXT,
                total_ep      INTEGER DEFAULT 0,
                year          INTEGER,
                season        TEXT,
                score         REAL DEFAULT 0,
                is_active     INTEGER DEFAULT 1,
                added_by      INTEGER,
                added_at      TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Epizodlar (kanal file_id saqlanadi)
            CREATE TABLE IF NOT EXISTS episodes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id      INTEGER NOT NULL,
                ep_number     INTEGER NOT NULL,
                title         TEXT,
                file_id       TEXT,
                file_unique_id TEXT,
                message_id    INTEGER,
                duration      INTEGER DEFAULT 0,
                quality       TEXT DEFAULT '480p',
                subtitles     TEXT DEFAULT 'none',
                views         INTEGER DEFAULT 0,
                added_by      INTEGER,
                added_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(anime_id, ep_number),
                FOREIGN KEY(anime_id) REFERENCES anime_list(id)
            );

            -- Sevimlilar
            CREATE TABLE IF NOT EXISTS favorites (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                anime_id      INTEGER NOT NULL,
                added_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, anime_id)
            );

            -- Ko'rish tarixi
            CREATE TABLE IF NOT EXISTS watch_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                anime_id      INTEGER NOT NULL,
                ep_number     INTEGER,
                watched_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Reytinglar (1-10)
            CREATE TABLE IF NOT EXISTS ratings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                anime_id      INTEGER NOT NULL,
                score         INTEGER NOT NULL,
                rated_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, anime_id)
            );

            -- Izohlar
            CREATE TABLE IF NOT EXISTS comments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                anime_id      INTEGER NOT NULL,
                text          TEXT NOT NULL,
                is_approved   INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Bildirishnomalar (yangi epizod chiqqanda)
            CREATE TABLE IF NOT EXISTS subscriptions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                anime_id      INTEGER NOT NULL,
                UNIQUE(user_id, anime_id)
            );

            -- Referral
            CREATE TABLE IF NOT EXISTS referrals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id   INTEGER NOT NULL,
                referred_id   INTEGER NOT NULL,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(referred_id)
            );

            -- Umumiy statistika loglari
            CREATE TABLE IF NOT EXISTS action_logs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                action        TEXT,
                data          TEXT,
                created_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Bot sozlamalari (runtime)
            CREATE TABLE IF NOT EXISTS bot_settings (
                key           TEXT PRIMARY KEY,
                value         TEXT DEFAULT '',
                updated_at    TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Delegat adminlar (root adminlardan tashqari)
            CREATE TABLE IF NOT EXISTS admins (
                user_id       INTEGER PRIMARY KEY,
                added_by      INTEGER,
                added_at      TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- E'lon uchun ulangan kanallar
            CREATE TABLE IF NOT EXISTS publish_channels (
                channel_id    TEXT PRIMARY KEY,
                title         TEXT,
                added_by      INTEGER,
                added_at      TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_fav_user    ON favorites(user_id);
            CREATE INDEX IF NOT EXISTS idx_hist_user   ON watch_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_ep_anime    ON episodes(anime_id);
            CREATE INDEX IF NOT EXISTS idx_sub_user    ON subscriptions(user_id);
            CREATE INDEX IF NOT EXISTS idx_rating      ON ratings(anime_id);
        """)
        await db.execute(
            "INSERT OR IGNORE INTO bot_settings(key, value) VALUES(?, ?)",
            ("storage_channel", ""),
        )
        await db.execute(
            "INSERT OR IGNORE INTO bot_settings(key, value) VALUES(?, ?)",
            ("subscribe_channel", ""),
        )
        await db.execute(
            "INSERT OR IGNORE INTO bot_settings(key, value) VALUES(?, ?)",
            ("subscribe_channel_id", ""),
        )
        await db.commit()
    logger.info("✅ Database tayyor")


# ═══════════════════════════════════════════════════════════════
#  USERS
# ═══════════════════════════════════════════════════════════════
async def register_user(user_id, username, first_name, ref_by=0):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM users WHERE id=?", (user_id,))
        exists = await cur.fetchone()
        if not exists:
            await db.execute(
                "INSERT INTO users(id,username,first_name,ref_by) VALUES(?,?,?,?)",
                (user_id, username or "", first_name or "", ref_by)
            )
            if ref_by:
                await db.execute(
                    "UPDATE users SET ref_count=ref_count+1 WHERE id=?", (ref_by,)
                )
                await db.execute(
                    "INSERT OR IGNORE INTO referrals(referrer_id,referred_id) VALUES(?,?)",
                    (ref_by, user_id)
                )
        else:
            await db.execute(
                "UPDATE users SET username=?,first_name=? WHERE id=?",
                (username or "", first_name or "", user_id)
            )
        await db.commit()


async def get_user(user_id) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_all_users() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id FROM users WHERE is_blocked=0")
        return [r[0] for r in await cur.fetchall()]


async def set_lang(user_id, lang):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET lang=? WHERE id=?", (lang, user_id))
        await db.commit()


# ═══════════════════════════════════════════════════════════════
#  ANIME
# ═══════════════════════════════════════════════════════════════
async def add_anime(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO anime_list
            (anilist_id,title_uz,title_en,title_jp,description,cover_image,
             banner_image,genres,status,total_ep,year,season,score,added_by)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(anilist_id) DO UPDATE SET
              title_en=excluded.title_en, description=excluded.description,
              cover_image=excluded.cover_image, status=excluded.status,
              total_ep=excluded.total_ep, score=excluded.score
        """, (
            data.get("anilist_id"), data.get("title_uz",""),
            data.get("title_en",""), data.get("title_jp",""),
            data.get("description",""), data.get("cover_image",""),
            data.get("banner_image",""), data.get("genres",""),
            data.get("status",""), data.get("total_ep",0),
            data.get("year"), data.get("season",""),
            data.get("score",0), data.get("added_by",0)
        ))
        await db.commit()
        # ID ni olish
        cur2 = await db.execute(
            "SELECT id FROM anime_list WHERE anilist_id=?", (data.get("anilist_id"),)
        )
        row = await cur2.fetchone()
    return row[0] if row else 0


async def get_anime_by_id(anime_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM anime_list WHERE id=?", (anime_id,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_anime_by_anilist(anilist_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM anime_list WHERE anilist_id=?", (anilist_id,))
        row = await cur.fetchone()
    return dict(row) if row else None


async def search_local_anime(query: str) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM anime_list
            WHERE is_active=1 AND (
                title_en LIKE ? OR title_jp LIKE ? OR title_uz LIKE ?
            )
            ORDER BY score DESC LIMIT 10
        """, (f"%{query}%", f"%{query}%", f"%{query}%"))
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_all_anime(page=1, per_page=20) -> list:
    offset = (page - 1) * per_page
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM anime_list WHERE is_active=1 ORDER BY added_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def update_anime_ep_count(anime_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM episodes WHERE anime_id=?", (anime_id,)
        )
        count = (await cur.fetchone())[0]
        await db.execute(
            "UPDATE anime_list SET total_ep=? WHERE id=?", (count, anime_id)
        )
        await db.commit()


async def delete_anime(anime_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE anime_list SET is_active=0 WHERE id=?", (anime_id,))
        await db.commit()


# ═══════════════════════════════════════════════════════════════
#  EPISODES
# ═══════════════════════════════════════════════════════════════
async def add_episode(data: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO episodes
            (anime_id,ep_number,title,file_id,file_unique_id,message_id,
             duration,quality,subtitles,added_by)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(anime_id,ep_number) DO UPDATE SET
              file_id=excluded.file_id, file_unique_id=excluded.file_unique_id,
              message_id=excluded.message_id, quality=excluded.quality,
              subtitles=excluded.subtitles
        """, (
            data["anime_id"], data["ep_number"],
            data.get("title",""), data["file_id"],
            data.get("file_unique_id",""), data.get("message_id",0),
            data.get("duration",0), data.get("quality","480p"),
            data.get("subtitles","none"), data.get("added_by",0)
        ))
        await db.commit()
        row_id = cur.lastrowid
    await update_anime_ep_count(data["anime_id"])
    return row_id


async def get_episodes(anime_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM episodes WHERE anime_id=? ORDER BY ep_number",
            (anime_id,)
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_episode(anime_id: int, ep_number: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM episodes WHERE anime_id=? AND ep_number=?",
            (anime_id, ep_number)
        )
        row = await cur.fetchone()
    return dict(row) if row else None


async def increment_views(episode_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE episodes SET views=views+1 WHERE id=?", (episode_id,))
        await db.commit()


async def delete_episode(anime_id: int, ep_number: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM episodes WHERE anime_id=? AND ep_number=?",
            (anime_id, ep_number)
        )
        await db.commit()
    await update_anime_ep_count(anime_id)


# ═══════════════════════════════════════════════════════════════
#  FAVORITES
# ═══════════════════════════════════════════════════════════════
async def add_favorite(user_id, anime_id) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO favorites(user_id,anime_id) VALUES(?,?)",
                (user_id, anime_id)
            )
            await db.commit()
        return True
    except Exception:
        return False


async def remove_favorite(user_id, anime_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM favorites WHERE user_id=? AND anime_id=?", (user_id, anime_id)
        )
        await db.commit()


async def is_favorite(user_id, anime_id) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM favorites WHERE user_id=? AND anime_id=?", (user_id, anime_id)
        )
        return (await cur.fetchone()) is not None


async def get_favorites(user_id) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT a.*, f.added_at as fav_added
            FROM favorites f JOIN anime_list a ON f.anime_id=a.id
            WHERE f.user_id=? AND a.is_active=1
            ORDER BY f.added_at DESC
        """, (user_id,))
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
#  WATCH HISTORY
# ═══════════════════════════════════════════════════════════════
async def add_history(user_id, anime_id, ep_number):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO watch_history(user_id,anime_id,ep_number) VALUES(?,?,?)",
            (user_id, anime_id, ep_number)
        )
        await db.commit()


async def get_history(user_id, limit=20) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT h.ep_number, h.watched_at, a.title_en, a.title_jp, a.id as anime_id, a.cover_image
            FROM watch_history h JOIN anime_list a ON h.anime_id=a.id
            WHERE h.user_id=? ORDER BY h.watched_at DESC LIMIT ?
        """, (user_id, limit))
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_last_watched(user_id, anime_id) -> int:
    """Oxirgi ko'rilgan epizod raqami"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT ep_number FROM watch_history
            WHERE user_id=? AND anime_id=?
            ORDER BY watched_at DESC LIMIT 1
        """, (user_id, anime_id))
        row = await cur.fetchone()
    return row[0] if row else 0


# ═══════════════════════════════════════════════════════════════
#  RATINGS & COMMENTS
# ═══════════════════════════════════════════════════════════════
async def set_rating(user_id, anime_id, score):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO ratings(user_id,anime_id,score) VALUES(?,?,?)
            ON CONFLICT(user_id,anime_id) DO UPDATE SET score=excluded.score
        """, (user_id, anime_id, score))
        await db.commit()


async def get_anime_rating(anime_id) -> tuple[float, int]:
    """(o'rtacha ball, ovozlar soni)"""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT AVG(score), COUNT(*) FROM ratings WHERE anime_id=?", (anime_id,)
        )
        row = await cur.fetchone()
    avg = round(row[0] or 0, 1)
    count = row[1] or 0
    return avg, count


async def get_user_rating(user_id, anime_id) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT score FROM ratings WHERE user_id=? AND anime_id=?", (user_id, anime_id)
        )
        row = await cur.fetchone()
    return row[0] if row else 0


async def add_comment(user_id, anime_id, text) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO comments(user_id,anime_id,text) VALUES(?,?,?)",
            (user_id, anime_id, text)
        )
        await db.commit()
    return cur.lastrowid


async def get_comments(anime_id, approved_only=True) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT c.*, u.first_name, u.username FROM comments c JOIN users u ON c.user_id=u.id WHERE c.anime_id=?"
        params = [anime_id]
        if approved_only:
            q += " AND c.is_approved=1"
        q += " ORDER BY c.created_at DESC LIMIT 10"
        cur = await db.execute(q, params)
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def approve_comment(comment_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE comments SET is_approved=1 WHERE id=?", (comment_id,))
        await db.commit()


async def get_pending_comments() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT c.*, u.first_name, a.title_en
            FROM comments c
            JOIN users u ON c.user_id=u.id
            JOIN anime_list a ON c.anime_id=a.id
            WHERE c.is_approved=0
            ORDER BY c.created_at DESC LIMIT 20
        """)
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
#  SUBSCRIPTIONS (bildirishnomalar)
# ═══════════════════════════════════════════════════════════════
async def subscribe_anime(user_id, anime_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO subscriptions(user_id,anime_id) VALUES(?,?)",
            (user_id, anime_id)
        )
        await db.commit()


async def unsubscribe_anime(user_id, anime_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM subscriptions WHERE user_id=? AND anime_id=?",
            (user_id, anime_id)
        )
        await db.commit()


async def is_subscribed_anime(user_id, anime_id) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM subscriptions WHERE user_id=? AND anime_id=?",
            (user_id, anime_id)
        )
        return (await cur.fetchone()) is not None


async def get_anime_subscribers(anime_id) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id FROM subscriptions WHERE anime_id=?", (anime_id,)
        )
        return [r[0] for r in await cur.fetchall()]


# ═══════════════════════════════════════════════════════════════
#  STATS
# ═══════════════════════════════════════════════════════════════
async def log_action(user_id, action, data=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO action_logs(user_id,action,data) VALUES(?,?,?)",
            (user_id, action, data)
        )
        await db.commit()


async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async def count(q, p=()):
            cur = await db.execute(q, p)
            return (await cur.fetchone())[0]

        return {
            "total_users":    await count("SELECT COUNT(*) FROM users WHERE is_blocked=0"),
            "today_users":    await count("SELECT COUNT(DISTINCT user_id) FROM action_logs WHERE created_at>=date('now','-1 day')"),
            "total_anime":    await count("SELECT COUNT(*) FROM anime_list WHERE is_active=1"),
            "total_episodes": await count("SELECT COUNT(*) FROM episodes"),
            "total_views":    await count("SELECT COALESCE(SUM(views),0) FROM episodes"),
            "total_favorites":await count("SELECT COUNT(*) FROM favorites"),
            "total_ratings":  await count("SELECT COUNT(*) FROM ratings"),
            "total_comments": await count("SELECT COUNT(*) FROM comments WHERE is_approved=1"),
        }


async def get_top_anime_local(limit=10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT a.*, COALESCE(AVG(r.score),0) as avg_rating, COUNT(r.id) as vote_count
            FROM anime_list a LEFT JOIN ratings r ON a.id=r.anime_id
            WHERE a.is_active=1
            GROUP BY a.id ORDER BY avg_rating DESC, vote_count DESC LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_most_viewed(limit=10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT a.*, COALESCE(SUM(e.views),0) as total_views
            FROM anime_list a LEFT JOIN episodes e ON a.id=e.anime_id
            WHERE a.is_active=1
            GROUP BY a.id ORDER BY total_views DESC LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
#  RUNTIME SETTINGS / ADMINS
# ═══════════════════════════════════════════════════════════════
async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM bot_settings WHERE key=?", (key,))
        row = await cur.fetchone()
    return (row[0] if row else default) or default


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO bot_settings(key, value, updated_at)
            VALUES(?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        await db.commit()


def is_root_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def is_admin(user_id: int) -> bool:
    if is_root_admin(user_id):
        return True
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
        return (await cur.fetchone()) is not None


async def add_delegated_admin(user_id: int, added_by: int) -> None:
    if is_root_admin(user_id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO admins(user_id, added_by) VALUES(?, ?)",
            (user_id, added_by),
        )
        await db.commit()


async def remove_delegated_admin(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
        await db.commit()


async def list_delegated_admins() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT user_id, added_by, added_at FROM admins ORDER BY added_at DESC")
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_all_admin_ids() -> list[int]:
    ids = set(ADMIN_IDS)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM admins")
        ids.update(r[0] for r in await cur.fetchall())
    return sorted(ids)


async def add_publish_channel(channel_id: str, title: str, added_by: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO publish_channels(channel_id, title, added_by)
            VALUES(?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                title=excluded.title,
                added_by=excluded.added_by
            """,
            (channel_id, title, added_by),
        )
        await db.commit()


async def remove_publish_channel(channel_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM publish_channels WHERE channel_id=?", (channel_id,))
        await db.commit()


async def get_publish_channels() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT channel_id, title, added_by, added_at FROM publish_channels ORDER BY added_at DESC"
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


