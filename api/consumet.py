"""
Consumet API — epizodlar va download linklar
"""
import aiohttp
import logging
from config import CONSUMET_API, CONSUMET_BACKUP

logger = logging.getLogger(__name__)


async def _get(path: str, params: dict = None) -> dict | None:
    for base in [CONSUMET_API, CONSUMET_BACKUP]:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{base}{path}", params=params,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as r:
                    if r.status == 200:
                        return await r.json()
        except Exception as e:
            logger.warning(f"Consumet ({base}): {e}")
    return None


async def search_gogoanime(query: str) -> list:
    r = await _get(f"/anime/gogoanime/{query}")
    return (r or {}).get("results", [])[:5]


async def get_anime_info(anime_id: str) -> dict | None:
    return await _get(f"/anime/gogoanime/info/{anime_id}")


async def get_episode_sources(episode_id: str, server: str = "gogocdn") -> dict | None:
    return await _get(f"/anime/gogoanime/watch/{episode_id}", {"server": server})


def extract_sources(data: dict) -> list:
    return (data or {}).get("sources", [])


def best_source(data: dict) -> tuple[str, str]:
    sources = extract_sources(data)
    if not sources:
        return "", "N/A"
    for q in ["1080p", "720p", "480p", "360p", "default"]:
        for s in sources:
            if q in s.get("quality", "").lower():
                return s.get("url", ""), s.get("quality", q)
    return sources[0].get("url", ""), sources[0].get("quality", "default")


def format_sources(data: dict) -> str:
    sources = extract_sources(data)
    if not sources:
        return "❌ Manbalar topilmadi"
    lines = ["📥 <b>Yuklab olish:</b>\n"]
    for s in sources[:5]:
        q = s.get("quality", "default")
        url = s.get("url", "")
        icon = "🎬" if ".m3u8" in url else "📥"
        lines.append(f'{icon} <a href="{url}">{q}</a>')
    subs = (data or {}).get("subtitles", [])
    if subs:
        lines.append("\n📝 <b>Subtitles:</b>")
        for sub in subs[:3]:
            lines.append(f'  • <a href="{sub["url"]}">{sub.get("lang", "?")}</a>')
    return "\n".join(lines)
