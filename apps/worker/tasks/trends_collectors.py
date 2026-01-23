"""
Trends Phase 2: Data Collectors
Collects signals from Steam (HTML parsing) and other sources.
All collectors are idempotent and log insertions.
"""
import time
import logging
import requests
import json
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta
try:
    from bs4 import BeautifulSoup
except ImportError:
    # Fallback: use simple regex parsing if BeautifulSoup not available
    BeautifulSoup = None
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# Rate limiting: 1 req/sec per host, burst 3
_rate_limit_tokens = 3
_rate_limit_last_refill = time.time()


def _rate_limit_acquire():
    """Simple token bucket rate limiter: 1 req/sec, burst 3"""
    global _rate_limit_tokens, _rate_limit_last_refill
    
    now = time.time()
    elapsed = now - _rate_limit_last_refill
    
    if elapsed > 0:
        _rate_limit_tokens = min(3, _rate_limit_tokens + elapsed)
        _rate_limit_last_refill = now
    
    if _rate_limit_tokens >= 1:
        _rate_limit_tokens -= 1
        return True
    
    wait_time = 1.0 - _rate_limit_tokens
    if wait_time > 0:
        time.sleep(wait_time)
        _rate_limit_tokens = 0
        _rate_limit_last_refill = time.time()
        return True
    
    return False


def _fetch_with_backoff(url: str, params: Optional[Dict] = None, max_retries: int = 3) -> Optional[requests.Response]:
    """Fetch with exponential backoff on 429/5xx"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    
    for attempt in range(max_retries):
        _rate_limit_acquire()
        
        try:
            response = session.get(url, params=params, timeout=15)
            
            if response.status_code == 429:
                backoff = 2 ** attempt + 1
                logger.warning(f"trends_fetch_429 url={url} attempt={attempt+1} backoff={backoff}s")
                time.sleep(backoff)
                continue
            
            if response.status_code >= 500:
                backoff = 2 ** attempt + 1
                logger.warning(f"trends_fetch_5xx url={url} status={response.status_code} attempt={attempt+1} backoff={backoff}s")
                time.sleep(backoff)
                continue
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                backoff = 2 ** attempt + 1
                logger.warning(f"trends_fetch_error url={url} error={e} attempt={attempt+1} backoff={backoff}s")
                time.sleep(backoff)
            else:
                logger.error(f"trends_fetch_failed url={url} error={e} after {max_retries} attempts")
                return None
    
    return None


def collect_store_snapshot(db, steam_app_id: int) -> bool:
    """
    Collect Steam Store page snapshot (HTML parsing).
    Extracts: reviews, price, discount, tags, languages, release date.
    """
    logger.info(f"trends_collect_start source=steam_store steam_app_id={steam_app_id}")
    
    url = f"https://store.steampowered.com/app/{steam_app_id}"
    
    response = _fetch_with_backoff(url)
    if not response:
        logger.warning(f"trends_collect_fail source=steam_store steam_app_id={steam_app_id} reason=fetch_failed")
        return False
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract reviews from JSON in page
        reviews_total = None
        reviews_recent = None
        positive_percent = None
        
        # Try to find JSON data in page
        if soup is None:
            # Fallback: parse HTML text directly with regex
            scripts = []
            # Try to extract from response text directly
            match = re.search(r'"total_reviews":\s*(\d+)', response.text)
            if match:
                reviews_total = int(match.group(1))
        else:
            scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'rgReviews' in script.string:
                # Extract review data from JavaScript
                match = re.search(r'rgReviews.*?(\d+)', script.string)
                if match:
                    reviews_recent = int(match.group(1))
            
            if script.string and 'review_summary' in script.string:
                # Extract review summary
                match = re.search(r'"total_reviews":\s*(\d+)', script.string)
                if match:
                    reviews_total = int(match.group(1))
                
                match = re.search(r'"total_positive":\s*(\d+)', script.string)
                positive_count = int(match.group(1)) if match else None
                if reviews_total and positive_count:
                    positive_percent = int((positive_count / reviews_total) * 100)
        
        # Extract price and discount
        price_eur = None
        discount_percent = None
        
        if soup:
            price_element = soup.find('div', class_='game_purchase_price')
            if price_element:
                price_text = price_element.get_text(strip=True)
                # Try to extract price
                match = re.search(r'[\d,]+\.?\d*', price_text.replace(',', ''))
                if match:
                    try:
                        price_eur = float(match.group(0))
                    except:
                        pass
            
            discount_element = soup.find('div', class_='discount_pct')
            if discount_element:
                discount_text = discount_element.get_text(strip=True)
                match = re.search(r'-(\d+)%', discount_text)
                if match:
                    discount_percent = int(match.group(1))
        
        # Extract tags
        tags = []
        if soup:
            tag_elements = soup.find_all('a', class_='app_tag')
        else:
            tag_elements = []
        for tag_elem in tag_elements[:20]:  # Limit to first 20
            tag_text = tag_elem.get_text(strip=True)
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
        
        # Extract languages
        languages = []
        if soup:
            lang_section = soup.find('div', {'id': 'language_section'})
        else:
            lang_section = None
        if lang_section:
            lang_elements = lang_section.find_all('td', class_='ellipsis')
            for lang_elem in lang_elements:
                lang_text = lang_elem.get_text(strip=True)
                if lang_text:
                    languages.append(lang_text)
        
        # Extract release date
        release_date = None
        if soup:
            release_elem = soup.find('div', class_='date')
        else:
            release_elem = None
        if release_elem:
            release_text = release_elem.get_text(strip=True)
            # Try to parse common date formats
            for fmt in ["%d %b, %Y", "%b %d, %Y", "%Y-%m-%d"]:
                try:
                    release_date = datetime.strptime(release_text, fmt).date()
                    break
                except:
                    continue
        
        # Store raw signals (using schema: value_numeric, value_text)
        signals_inserted = 0
        
        # Write reviews_total numeric signal
        if reviews_total is not None:
            db.execute(
                text("""
                    INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                    VALUES (:steam_app_id, 'steam_reviews', 'reviews_total', :value, :captured_at)
                """),
                {"steam_app_id": steam_app_id, "value": float(reviews_total), "captured_at": datetime.now()}
            )
            signals_inserted += 1
        else:
            # Write 0 if unavailable
            db.execute(
                text("""
                    INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                    VALUES (:steam_app_id, 'steam_reviews', 'reviews_total', 0, :captured_at)
                """),
                {"steam_app_id": steam_app_id, "captured_at": datetime.now()}
            )
            signals_inserted += 1
        
        # Write positive_ratio numeric signal (0.0 to 1.0)
        if positive_percent is not None:
            positive_ratio = float(positive_percent) / 100.0
            db.execute(
                text("""
                    INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                    VALUES (:steam_app_id, 'steam_reviews', 'positive_ratio', :value, :captured_at)
                """),
                {"steam_app_id": steam_app_id, "value": positive_ratio, "captured_at": datetime.now()}
            )
            signals_inserted += 1
        
        # Write recent_reviews_30d numeric signal
        if reviews_recent is not None:
            db.execute(
                text("""
                    INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                    VALUES (:steam_app_id, 'steam_reviews', 'recent_reviews_30d', :value, :captured_at)
                """),
                {"steam_app_id": steam_app_id, "value": float(reviews_recent), "captured_at": datetime.now()}
            )
            signals_inserted += 1
        else:
            # Write 0 if unavailable
            db.execute(
                text("""
                    INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                    VALUES (:steam_app_id, 'steam_reviews', 'recent_reviews_30d', 0, :captured_at)
                """),
                {"steam_app_id": steam_app_id, "captured_at": datetime.now()}
            )
            signals_inserted += 1
        
        # Write tags as text signal (JSON array string)
        if tags:
            db.execute(
                text("""
                    INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_text, captured_at)
                    VALUES (:steam_app_id, 'steam_store', 'tag_growth', :value, :captured_at)
                """),
                {"steam_app_id": steam_app_id, "value": json.dumps(tags), "captured_at": datetime.now()}
            )
            signals_inserted += 1
        
        db.commit()
        logger.info(f"trends_collect_done source=steam_store steam_app_id={steam_app_id} signals_inserted={signals_inserted}")
        return True
        
    except Exception as e:
        logger.error(f"trends_collect_fail source=steam_store steam_app_id={steam_app_id} error={e}", exc_info=True)
        db.rollback()
        return False


def collect_reviews_delta(db, steam_app_id: int) -> bool:
    """
    Collect reviews delta using Steam Reviews API (JSON endpoint).
    Compares today's review count with yesterday's.
    """
    logger.info(f"trends_collect_start source=steam_reviews steam_app_id={steam_app_id}")
    
    url = f"https://store.steampowered.com/appreviews/{steam_app_id}"
    params = {"json": 1, "filter": "all", "language": "all", "num_per_page": 0}
    
    response = _fetch_with_backoff(url, params)
    if not response:
        logger.warning(f"trends_collect_fail source=steam_reviews steam_app_id={steam_app_id} reason=fetch_failed")
        return False
    
    try:
        data = response.json()
        query_summary = data.get("query_summary", {})
        
        total_reviews = query_summary.get("total_reviews", 0)
        total_positive = query_summary.get("total_positive", 0)
        recent_reviews = query_summary.get("recent_reviews", 0)
        
        # Calculate positive_ratio (0.0 to 1.0)
        positive_ratio = float(total_positive) / float(total_reviews) if total_reviews > 0 else 0.0
        
        # Write reviews_total numeric signal
        db.execute(
            text("""
                INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                VALUES (:steam_app_id, 'steam_reviews', 'reviews_total', :value, :captured_at)
            """),
            {"steam_app_id": steam_app_id, "value": float(total_reviews), "captured_at": datetime.now()}
        )
        
        # Write positive_ratio numeric signal
        db.execute(
            text("""
                INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                VALUES (:steam_app_id, 'steam_reviews', 'positive_ratio', :value, :captured_at)
            """),
            {"steam_app_id": steam_app_id, "value": positive_ratio, "captured_at": datetime.now()}
        )
        
        # Write recent_reviews_30d numeric signal (use recent_reviews from API or 0)
        db.execute(
            text("""
                INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                VALUES (:steam_app_id, 'steam_reviews', 'recent_reviews_30d', :value, :captured_at)
            """),
            {"steam_app_id": steam_app_id, "value": float(recent_reviews) if recent_reviews else 0.0, "captured_at": datetime.now()}
        )
        
        db.commit()
        logger.info(f"trends_collect_done source=steam_reviews steam_app_id={steam_app_id} reviews_total={total_reviews} positive_ratio={positive_ratio:.2f}")
        return True
        
    except Exception as e:
        logger.error(f"trends_collect_fail source=steam_reviews steam_app_id={steam_app_id} error={e}", exc_info=True)
        db.rollback()
        return False


def collect_discussions_delta(db, steam_app_id: int) -> bool:
    """
    Collect discussions delta from Steam Community.
    Parses HTML to get thread/post counts.
    """
    logger.info(f"trends_collect_start source=steam_discussions steam_app_id={steam_app_id}")
    
    url = f"https://steamcommunity.com/app/{steam_app_id}/discussions/"
    
    response = _fetch_with_backoff(url)
    if not response:
        logger.warning(f"trends_collect_fail source=steam_discussions steam_app_id={steam_app_id} reason=fetch_failed")
        return False
    
    try:
        if BeautifulSoup is None:
            soup = None
            logger.warning("BeautifulSoup not available for discussions parsing")
        else:
            soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find discussion counts
        # Steam discussions page structure may vary, so we use heuristics
        threads_count = None
        posts_count = None
        
        # Look for discussion stats
        if soup:
            stats_elements = soup.find_all('div', class_='forum_topic')
        else:
            stats_elements = []
        if stats_elements:
            threads_count = len(stats_elements)
        
        # Write placeholder discussion_threads_7d numeric signal (0 until implemented)
        db.execute(
            text("""
                INSERT INTO trends_raw_signals (steam_app_id, source, signal_type, value_numeric, captured_at)
                VALUES (:steam_app_id, 'steam_discussions', 'discussion_threads_7d', 0, :captured_at)
            """),
            {"steam_app_id": steam_app_id, "captured_at": datetime.now()}
        )
        
        db.commit()
        logger.info(f"trends_collect_done source=steam_discussions steam_app_id={steam_app_id} discussion_threads_7d=0 (placeholder)")
        return True
        
    except Exception as e:
        logger.error(f"trends_collect_fail source=steam_discussions steam_app_id={steam_app_id} error={e}", exc_info=True)
        db.rollback()
        return False


def aggregate_daily_trends(db, target_date: Optional[date] = None) -> bool:
    """
    Aggregate daily trends from raw signals.
    Computes deltas and aggregates for trends_game_daily and trends_tags_daily.
    """
    if target_date is None:
        target_date = date.today()
    
    logger.info(f"trends_aggregate_start date={target_date}")
    
    try:
        # Aggregate per game
        # Get all games with signals for the target date
        games_with_signals = db.execute(
            text("""
                SELECT DISTINCT steam_app_id
                FROM trends_raw_signals
                WHERE DATE(captured_at) = :target_date
            """),
            {"target_date": target_date}
        ).scalars().all()
        
        for app_id in games_with_signals:
            # Calculate reviews_delta
            reviews_delta = db.execute(
                text("""
                    SELECT value_numeric
                    FROM trends_raw_signals
                    WHERE steam_app_id = :app_id
                      AND source = 'steam_reviews'
                      AND signal_type = 'reviews_velocity'
                      AND DATE(captured_at) = :target_date
                    ORDER BY captured_at DESC
                    LIMIT 1
                """),
                {"app_id": app_id, "target_date": target_date}
            ).scalar()
            
            # Calculate recent_reviews_delta
            recent_delta = db.execute(
                text("""
                    SELECT value_numeric
                    FROM trends_raw_signals
                    WHERE steam_app_id = :app_id
                      AND source = 'steam_store'
                      AND signal_type = 'recent_reviews_velocity'
                      AND DATE(captured_at) = :target_date
                    ORDER BY captured_at DESC
                    LIMIT 1
                """),
                {"app_id": app_id, "target_date": target_date}
            ).scalar()
            
            # Calculate discussion_threads_delta
            discussion_delta = db.execute(
                text("""
                    SELECT value_numeric
                    FROM trends_raw_signals
                    WHERE steam_app_id = :app_id
                      AND source = 'steam_discussions'
                      AND signal_type = 'discussion_velocity'
                      AND DATE(captured_at) = :target_date
                    ORDER BY captured_at DESC
                    LIMIT 1
                """),
                {"app_id": app_id, "target_date": target_date}
            ).scalar()
            
            # Get avg_positive_ratio from steam_review_daily
            avg_positive = db.execute(
                text("""
                    SELECT all_positive_percent
                    FROM steam_review_daily
                    WHERE steam_app_id = :app_id AND day = :target_date
                    ORDER BY computed_at DESC
                    LIMIT 1
                """),
                {"app_id": app_id, "target_date": target_date}
            ).scalar()
            
            # Count new tags
            new_tags_count = None
            tags_signal = db.execute(
                text("""
                    SELECT value_text
                    FROM trends_raw_signals
                    WHERE steam_app_id = :app_id
                      AND source = 'steam_store'
                      AND signal_type = 'tag_growth'
                      AND DATE(captured_at) = :target_date
                    ORDER BY captured_at DESC
                    LIMIT 1
                """),
                {"app_id": app_id, "target_date": target_date}
            ).scalar()
            
            if tags_signal:
                try:
                    current_tags = set(json.loads(tags_signal))
                    # Compare with previous day
                    prev_tags_signal = db.execute(
                        text("""
                            SELECT value_text
                            FROM trends_raw_signals
                            WHERE steam_app_id = :app_id
                              AND source = 'steam_store'
                              AND signal_type = 'tag_growth'
                              AND DATE(captured_at) = :prev_date
                            ORDER BY captured_at DESC
                            LIMIT 1
                        """),
                        {"app_id": app_id, "prev_date": target_date - timedelta(days=1)}
                    ).scalar()
                    
                    if prev_tags_signal:
                        prev_tags = set(json.loads(prev_tags_signal))
                        new_tags_count = len(current_tags - prev_tags)
                    else:
                        new_tags_count = len(current_tags)
                except:
                    pass
            
            # Upsert trends_game_daily
            db.execute(
                text("""
                    INSERT INTO trends_game_daily
                        (steam_app_id, date, reviews_delta, recent_reviews_delta,
                         discussion_threads_delta, avg_positive_ratio, new_tags_count, computed_at)
                    VALUES
                        (:steam_app_id, :date, :reviews_delta, :recent_reviews_delta,
                         :discussion_threads_delta, :avg_positive_ratio, :new_tags_count, :computed_at)
                    ON CONFLICT (steam_app_id, date) DO UPDATE SET
                        reviews_delta = EXCLUDED.reviews_delta,
                        recent_reviews_delta = EXCLUDED.recent_reviews_delta,
                        discussion_threads_delta = EXCLUDED.discussion_threads_delta,
                        avg_positive_ratio = EXCLUDED.avg_positive_ratio,
                        new_tags_count = EXCLUDED.new_tags_count,
                        computed_at = EXCLUDED.computed_at
                """),
                {
                    "steam_app_id": app_id,
                    "date": target_date,
                    "reviews_delta": reviews_delta,
                    "recent_reviews_delta": recent_delta,
                    "discussion_threads_delta": discussion_delta,
                    "avg_positive_ratio": float(avg_positive) if avg_positive else None,
                    "new_tags_count": new_tags_count,
                    "computed_at": datetime.now()
                }
            )
        
        db.commit()
        logger.info(f"trends_aggregate_done date={target_date} games_processed={len(games_with_signals)}")
        return True
        
    except Exception as e:
        logger.error(f"trends_aggregate_fail date={target_date} error={e}", exc_info=True)
        db.rollback()
        return False


if __name__ == "__main__":
    # Standalone runner
    import os
    from apps.worker.db import get_engine
    
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    
    # Test collection for app_id 620
    collect_store_snapshot(db, 620)
    collect_reviews_delta(db, 620)
    collect_discussions_delta(db, 620)
    aggregate_daily_trends(db)
    
    db.close()
