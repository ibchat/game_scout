"""
Relaunch Scout Configuration
Конфигурация для поиска недореализованных игр в Rebound Window.
"""

# ============================================================
# Rebound Window (временное окно)
# ============================================================
DEFAULT_MIN_MONTHS = 6
DEFAULT_MAX_MONTHS = 24

# Расширенное окно (опция)
EXTENDED_MIN_MONTHS = 3
EXTENDED_MAX_MONTHS = 36

# ============================================================
# Reviews фильтры
# ============================================================
DEFAULT_MIN_REVIEWS = 50
DEFAULT_MAX_REVIEWS = 10000
DEFAULT_MEGA_HIT_REVIEWS = 50000  # Жёсткое исключение

# ============================================================
# Исключения
# ============================================================
DEFAULT_EXCLUDE_F2P = True
DEFAULT_EXCLUDE_EARLY_ACCESS = False  # опция

# Жёсткие исключения app_id (мега-хиты, сервисные гиганты)
EXCLUDE_APP_IDS = {
    570,      # Dota 2
    730,      # CS2
    1091500,  # Cyberpunk 2077
    578080,   # PUBG
    271590,   # GTA V
    1174180,  # Red Dead Redemption 2
    1172620,  # Sea of Thieves
    252490,   # Rust
    440,      # Team Fortress 2
    359550,   # Tom Clancy's Rainbow Six Siege
}

# Исключения по имени (lowercase contains)
EXCLUDE_NAME_CONTAINS = [
    "counter-strike",
    "dota",
    "cyberpunk",
    "pubg",
    "apex",
    "destiny",
    "warframe",
    "path of exile",
    "gta v",
    "grand theft auto",
    "genshin",
    "honkai",
    "roblox",
    "fortnite",
    "call of duty",
    "fifa",
    "nba 2k",
    "madden",
    "assassin's creed",
    "far cry",
    "watch dogs",
    "tom clancy",
    "rainbow six",
    "the elder scrolls",
    "fallout",
    "skyrim",
    "minecraft",
    "terraria",
    "stardew valley",
    "hollow knight",
    "dead cells",
    "celeste",
    "cuphead",
    "undertale",
    "the binding of isaac",
    "slay the spire",
    "hades",
    "risk of rain",
    "enter the gungeon",
    "nuclear throne",
    "spelunky",
    "super meat boy",
    "the witness",
    "braid",
    "limbo",
    "inside",
    "little nightmares",
    "ori and the",
    "hollow knight",
    "dead cells",
    "celeste",
    "cuphead",
    "undertale",
    "the binding of isaac",
    "slay the spire",
    "hades",
    "risk of rain",
    "enter the gungeon",
    "nuclear throne",
    "spelunky",
    "super meat boy",
    "the witness",
    "braid",
    "limbo",
    "inside",
    "little nightmares",
    "ori and the",
]

# Типы, которые не считаем игрой
EXCLUDE_TYPES = {"dlc", "demo", "music", "soundtrack", "video", "tool", "advertising"}

# ============================================================
# Steam Search: жанры для поиска
# ============================================================
STEAM_GENRES = [
    "Action",
    "Adventure",
    "RPG",
    "Strategy",
    "Simulation",
    "Indie",
    "Horror",
    "Roguelike",
    "Puzzle",
    "Survival",
    "Casual",
]

# ============================================================
# Steam Search: теги для поиска
# ============================================================
STEAM_TAGS = [
    "Indie",
    "Singleplayer",
    "Story Rich",
    "Atmospheric",
    "Experimental",
    "Stylized",
    "Early Access",
    "Pixel Graphics",
    "Anime",
    "Visual Novel",
    "Turn-Based",
]

# ============================================================
# Steam Search: пагинация
# ============================================================
DEFAULT_PAGE_START = 1
DEFAULT_PAGE_END = 15  # MVP: 15 страниц = ~300-700 игр

# ============================================================
# Scanner Version
# ============================================================
SCANNER_VERSION = "2.0.0-rebound-window"
