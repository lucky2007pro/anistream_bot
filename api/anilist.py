import re, aiohttp, logging
from datetime import datetime
from config import ANILIST_API, CACHE_TTL

logger = logging.getLogger(__name__)
_cache: dict = {}

def _cached(k):
    if k in _cache:
        d, t = _cache[k]
        if (datetime.now()-t).seconds < CACHE_TTL: return d
    return None

def _set(k, d): _cache[k] = (d, datetime.now())

async def _q(query, variables):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(ANILIST_API,
                json={"query": query, "variables": variables},
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200: return await r.json()
    except Exception as e:
        logger.error(f"AniList: {e}")
    return None

SEARCH_Q = """
query($s:String,$p:Int,$pp:Int){Page(page:$p,perPage:$pp){
  pageInfo{total hasNextPage}
  media(search:$s,type:ANIME,sort:SEARCH_MATCH){
    id title{romaji english}coverImage{large}
    description(asHtml:false) genres status episodes averageScore
    season seasonYear studios(isMain:true){nodes{name}}
  }}}"""

DETAIL_Q = """
query($id:Int){Media(id:$id,type:ANIME){
  id title{romaji english native}
  coverImage{extraLarge large}bannerImage
  description(asHtml:false) genres tags{name}
  status episodes averageScore popularity
  season seasonYear format duration
  startDate{year month day}
  studios(isMain:true){nodes{name}}
  nextAiringEpisode{episode airingAt}
  siteUrl
}}"""

TRENDING_Q = """
query($p:Int){Page(page:$p,perPage:20){
  media(type:ANIME,sort:TRENDING_DESC,status_not:NOT_YET_RELEASED){
    id title{romaji english}coverImage{large}
    averageScore episodes status genres
  }}}"""

TOP_Q = """
query($p:Int){Page(page:$p,perPage:20){
  media(type:ANIME,sort:SCORE_DESC,format_in:[TV,MOVIE,OVA]){
    id title{romaji english}coverImage{large}
    averageScore episodes status genres
  }}}"""

SEASONAL_Q = """
query($s:MediaSeason,$y:Int,$p:Int){Page(page:$p,perPage:20){
  media(type:ANIME,season:$s,seasonYear:$y,sort:POPULARITY_DESC){
    id title{romaji english}coverImage{large}
    averageScore episodes status genres
  }}}"""

async def search_anime(query, page=1, per_page=5):
    k = f"s:{query}:{page}"
    if c := _cached(k): return c
    r = await _q(SEARCH_Q, {"s": query, "p": page, "pp": per_page})
    if r and "data" in r:
        _set(k, r["data"]["Page"]); return r["data"]["Page"]

async def get_details(anime_id):
    k = f"d:{anime_id}"
    if c := _cached(k): return c
    r = await _q(DETAIL_Q, {"id": anime_id})
    if r and "data" in r:
        _set(k, r["data"]["Media"]); return r["data"]["Media"]

async def get_trending(page=1):
    k = f"tr:{page}"
    if c := _cached(k): return c
    r = await _q(TRENDING_Q, {"p": page})
    if r and "data" in r:
        d = r["data"]["Page"]["media"]; _set(k, d); return d
    return []

async def get_top(page=1):
    k = f"top:{page}"
    if c := _cached(k): return c
    r = await _q(TOP_Q, {"p": page})
    if r and "data" in r:
        d = r["data"]["Page"]["media"]; _set(k, d); return d
    return []

async def get_seasonal(page=1):
    m = datetime.now().month
    s = "WINTER" if m<=3 else "SPRING" if m<=6 else "SUMMER" if m<=9 else "FALL"
    y = datetime.now().year
    k = f"sea:{s}:{y}:{page}"
    if c := _cached(k): return c
    r = await _q(SEASONAL_Q, {"s": s, "y": y, "p": page})
    if r and "data" in r:
        d = r["data"]["Page"]["media"]; _set(k, d); return d
    return []

def get_title(a): return a.get("title",{}).get("english") or a.get("title",{}).get("romaji") or "?"

def clean_desc(t, lim=500):
    t = re.sub(r"<[^>]+>","",t or "")
    for old,new in [("&amp;","&"),("&lt;","<"),("&gt;",">"),("&quot;",'"')]: t=t.replace(old,new)
    return (t[:lim]+"...") if len(t)>lim else t

def format_card(a: dict, local: dict = None) -> str:
    """AniList anime + local DB ma'lumoti birlashtirilgan karta"""
    title_en = a.get("title",{}).get("english") or ""
    title_jp = a.get("title",{}).get("romaji") or ""
    title = title_en or title_jp
    desc = clean_desc(a.get("description") or "")
    score = a.get("averageScore") or 0
    score_str = f"⭐ {score/10:.1f}/10" if score else "⭐ N/A"
    ep_str = f"📺 {a.get('episodes')} epizod" if a.get("episodes") else "📺 Davom etmoqda"
    genres = " • ".join((a.get("genres") or [])[:4]) or "N/A"
    status_map = {"FINISHED":"✅ Tugagan","RELEASING":"🔄 Chiqmoqda",
                  "NOT_YET_RELEASED":"🕐 Kutilmoqda","CANCELLED":"❌ Bekor"}
    status = status_map.get(a.get("status",""),"❓")
    studios = [s["name"] for s in (a.get("studios") or {}).get("nodes",[])[:2]]
    studio = " • ".join(studios) or "N/A"
    s,y = a.get("season",""), a.get("seasonYear","")
    season_str = f"\n📅 {s} {y}" if s and y else ""
    nxt = a.get("nextAiringEpisode")
    nxt_str = f"\n⏰ Keyingi: {nxt['episode']}-epizod" if nxt else ""

    local_str = ""
    if local:
        ep_count = local.get("total_ep", 0)
        local_str = f"\n\n🗄 <b>Bazada:</b> {ep_count} epizod mavjud"

    return (
        f"🎌 <b>{title}</b>\n"
        f"<i>{title_jp if title_en else ''}</i>\n\n"
        f"{score_str}  {ep_str}  {status}\n"
        f"🎭 <b>Janr:</b> {genres}\n"
        f"🏢 <b>Studio:</b> {studio}"
        f"{season_str}{nxt_str}"
        f"{local_str}\n\n"
        f"📖 <b>Tavsif:</b>\n{desc}"
    )

def format_list_item(a, i):
    title = get_title(a)
    score = a.get("averageScore") or 0
    s = f"⭐{score/10:.1f}" if score else ""
    ep = f"• {a.get('episodes')}ep" if a.get("episodes") else ""
    icons = {"FINISHED":"✅","RELEASING":"🔄","NOT_YET_RELEASED":"🕐","CANCELLED":"❌"}
    st = icons.get(a.get("status",""),"")
    return f"{i}. {st} <b>{title}</b> {s} {ep}"
