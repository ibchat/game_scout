from __future__ import annotations

import os
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import create_engine, text

from apps.worker.celery_app import celery_app

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@postgres:5432/game_scout")
engine = create_engine(DATABASE_URL, future=True)

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return "[]"


def _fetch_appdetails(steam_app_id: str) -> Optional[Dict[str, Any]]:
    # Steam appdetails: https://store.steampowered.com/api/appdetails?appids=1091500&cc=us&l=en
    params = {"appids": steam_app_id, "cc": "us", "l": "en"}
    r = requests.get(STEAM_APPDETAILS_URL, params=params, timeout=20)
    r.raise_for_status()
    payload = r.json()

    node = payload.get(str(steam_app_id))
    if not node or not node.get("success"):
        return None
    return node.get("data") or None


def _extract_snapshot_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    price = None
    discount = 0
    is_on_sale = False
    price_overview = data.get("price_overview") or {}
    if price_overview:
        final = price_overview.get("final")
        if isinstance(final, (int, float)):
            price = float(final) / 100.0
        discount = int(price_overview.get("discount_percent") or 0)
        is_on_sale = discount > 0

    # reviews summary (Steam appdetails doesn't always contain counts; keep defaults)
    all_reviews_count = 0
    all_reviews_positive_percent = None
    recent_reviews_count = 0
    recent_reviews_positive_percent = None

    # tags/genres/languages/dev/publishers
    genres = [g.get("description") for g in (data.get("genres") or []) if g.get("description")]
    developers = list(data.get("developers") or [])
    publishers = list(data.get("publishers") or [])

    # Steam appdetails does not give languages array, only string "supported_languages"
    languages_raw = data.get("supported_languages") or ""
    # keep raw string in json so we don't lose info
    languages = [languages_raw] if languages_raw else []

    tags = []
    # appdetails doesn't return tags as list; it has "categories" etc.
    categories = data.get("categories") or []
    for c in categories:
        d = c.get("description")
        if d:
            tags.append(d)

    release_date = None
    rd = (data.get("release_date") or {}).get("date")
    # keep as text; DB column is timestamp, but we store null if not parseable
    # if you want parse later, do it in another step

    last_update_date = None  # not in appdetails reliably

    capsule_image_url = data.get("capsule_image") or data.get("header_image")
    header_image_url = data.get("header_image")
    trailer_url = None
    movies = data.get("movies") or []
    if movies:
        # best effort
        m0 = movies[0]
        trailer_url = (m0.get("webm") or {}).get("max") or (m0.get("mp4") or {}).get("max")

    return {
        "price_eur": price,
        "discount_percent": discount,
        "is_on_sale": bool(is_on_sale),
        "all_reviews_count": int(all_reviews_count),
        "all_reviews_positive_percent": all_reviews_positive_percent,
        "recent_reviews_count": int(recent_reviews_count),
        "recent_reviews_positive_percent": recent_reviews_positive_percent,
        "tags": tags,
        "genres": genres,
        "languages": languages,
        "developers": developers,
        "publishers": publishers,
        "capsule_image_url": capsule_image_url,
        "header_image_url": header_image_url,
        "trailer_url": trailer_url,
        "release_date": None,
        "last_update_date": None,
        "html_cache": None,
    }


@celery_app.task(name="apps.worker.tasks.collect_relaunch_steam.collect_relaunch_steam_task")
def collect_relaunch_steam_task(limit_apps: int = 50, limit_reviews: int = 200):
    """
    Collect minimal Steam data for relaunch apps.

    IMPORTANT:
    - This MVP version only stores a snapshot from Steam appdetails.
    - Reviews collection is left as 0 in this file unless you already have a reviews collector.
    """
    now = datetime.utcnow()
    inserted_snapshots = 0
    inserted_reviews = 0  # reserved for later

    with engine.connect() as conn:
        apps = conn.execute(
            text(
                """
                SELECT id, steam_app_id
                FROM relaunch_apps
                WHERE is_active = true
                ORDER BY added_at DESC
                LIMIT :lim
                """
            ),
            {"lim": limit_apps},
        ).mappings().all()

        for a in apps:
            app_id = str(a["id"])
            steam_app_id = str(a["steam_app_id"])

            data = _fetch_appdetails(steam_app_id)
            if not data:
                continue

            snap = _extract_snapshot_fields(data)

            conn.execute(
                text(
                    """
                    INSERT INTO relaunch_app_snapshots (
                        app_id, captured_at,
                        price_eur, discount_percent, is_on_sale,
                        all_reviews_count, all_reviews_positive_percent,
                        recent_reviews_count, recent_reviews_positive_percent,
                        tags, genres, languages, developers, publishers,
                        capsule_image_url, header_image_url, trailer_url,
                        release_date, last_update_date, html_cache
                    ) VALUES (
                        :app_id, :captured_at,
                        :price_eur, :discount_percent, :is_on_sale,
                        :all_reviews_count, :all_reviews_positive_percent,
                        :recent_reviews_count, :recent_reviews_positive_percent,
                        CAST(:tags AS json), CAST(:genres AS json), CAST(:languages AS json),
                        CAST(:developers AS json), CAST(:publishers AS json),
                        :capsule_image_url, :header_image_url, :trailer_url,
                        :release_date, :last_update_date, :html_cache
                    )
                    """
                ),
                {
                    "app_id": app_id,
                    "captured_at": now,
                    "price_eur": snap["price_eur"],
                    "discount_percent": snap["discount_percent"],
                    "is_on_sale": snap["is_on_sale"],
                    "all_reviews_count": snap["all_reviews_count"],
                    "all_reviews_positive_percent": snap["all_reviews_positive_percent"],
                    "recent_reviews_count": snap["recent_reviews_count"],
                    "recent_reviews_positive_percent": snap["recent_reviews_positive_percent"],
                    "tags": _safe_json_dumps(snap["tags"]),
                    "genres": _safe_json_dumps(snap["genres"]),
                    "languages": _safe_json_dumps(snap["languages"]),
                    "developers": _safe_json_dumps(snap["developers"]),
                    "publishers": _safe_json_dumps(snap["publishers"]),
                    "capsule_image_url": snap["capsule_image_url"],
                    "header_image_url": snap["header_image_url"],
                    "trailer_url": snap["trailer_url"],
                    "release_date": snap["release_date"],
                    "last_update_date": snap["last_update_date"],
                    "html_cache": snap["html_cache"],
                },
            )
            inserted_snapshots += 1

            conn.execute(
                text("UPDATE relaunch_apps SET last_snapshot_at = :ts WHERE id = :app_id"),
                {"ts": now, "app_id": app_id},
            )

        conn.commit()

    return {"status": "ok", "snapshots": inserted_snapshots, "reviews": inserted_reviews}
