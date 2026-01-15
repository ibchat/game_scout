"""Relaunch Scout configuration"""

RELAUNCH_CONFIG = {
    "rate_limits": {
        "rps_per_domain": 1.0,
        "max_concurrent_requests": 3,
        "jitter_ms_min": 150,
        "jitter_ms_max": 650,
        "timeout_seconds": 20,
        "retry_max_attempts": 4,
        "retry_backoff_base_seconds": 1.7,
        "retryable_status": [429, 500, 502, 503, 504],
    },
    "cache_ttl": {
        "store_html_hours": 24,
        "reviews_hours": 12,
        "ccu_minutes": 30,
    },
    "jobs": {
        "store_snapshot_daily_time": "02:30",
        "reviews_fetch_daily_time": "03:30",
        "ccu_every_minutes": 240,
        "score_recompute_weekday": "SUN",
        "score_recompute_time": "05:00",
    },
    "thresholds": {
        "all_reviews_percent_min": 70,
        "recent_reviews_percent_min": 65,
        "reviews_count_min_signal": 30,
        "broken_ratio_reject": 0.08,
        "last_update_months_reject": 18,
        "price_eur_max_no_brand": 29.99,
        "candidate_score_min": 70,
        "watchlist_score_min": 60,
        "review_velocity_min_per_30d": 5,
        "trend_window_days": 90,
        "recent_window_days": 30,
        "discount_spike_window_days": 14,
    },
    "weights": {
        "product_quality": 0.30,
        "marketing_failure": 0.25,
        "genre_mismatch": 0.20,
        "latent_audience": 0.15,
        "dev_signal": 0.10,
    },
    "fetch_limits": {
        "reviews_fetch_limit_per_app": 400,
        "reviews_lang_whitelist": ["english", "russian", "spanish", "german", "french", "schinese", "tchinese"],
        "store_sample_quotes": 3,
    },
    "phrases": {
        "broken_game": [
            "crash","crashes","crashing","bug","bugs","buggy","broken","unplayable",
            "softlock","stuck","game breaking","doesn't launch","won't launch",
            "freeze","freezes","freezing","save deleted","lost my save",
            "performance is terrible","unoptimized","stuttering"
        ],
        "marketing_fail": [
            "marketing","no marketing","bad trailer","trailer is bad","trailer doesn't show",
            "store page","steam page","capsule","cover art","thumbnail","icon",
            "deserves more attention","needs more attention","why is this not popular",
            "nobody knows","no one knows about this","hidden gem","underrated"
        ],
        "underrated": [
            "underrated","hidden gem","deserves more attention","should be more popular","criminally underrated"
        ],
        "expectation_mismatch": [
            "i expected","i thought it would be","not what i expected","misleading",
            "wrong tags","tags are wrong","not a roguelike","not roguelike",
            "marketed as","advertised as"
        ],
        "loop": [
            "addictive","one more run","replayable","can't stop playing","great loop",
            "satisfying","hooked","time flew"
        ],
        "systems": [
            "optimize","optimization","build","builder","automation","automate",
            "systems","systemic","simulation","management","strategy","crafting"
        ],
        "dev_positive": [
            "dev listens","developer listens","active dev","active developer",
            "frequent updates","dev responded","good support","great support"
        ],
    }
}
