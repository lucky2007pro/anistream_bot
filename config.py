import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(BASE_DIR / ".env")


def _parse_admin_ids(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: list[int] = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))


# Deploy uchun qo'shimcha sozlamalar
DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "anime_pro.db"))
LOG_FILE: str = os.getenv("LOG_FILE", str(BASE_DIR / "bot.log"))

# AniList API (bepul, key shart emas)
ANILIST_API = os.getenv("ANILIST_API", "https://graphql.anilist.co")

# Consumet API (agar ishlatilsa)
CONSUMET_API = os.getenv("CONSUMET_API", "https://api.consumet.org")
CONSUMET_BACKUP = os.getenv("CONSUMET_BACKUP", "https://consumet-api-three.vercel.app")

# Sahifalar
RESULTS_PER_PAGE = int(os.getenv("RESULTS_PER_PAGE", "5"))
EPISODES_PER_PAGE = int(os.getenv("EPISODES_PER_PAGE", "16"))
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))

# Reyting
MAX_RATING = int(os.getenv("MAX_RATING", "10"))
