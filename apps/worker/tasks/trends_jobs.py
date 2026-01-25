"""
Trends Jobs Processor
Processes trend_jobs table: fetches Steam data and writes to steam_app_facts/steam_review_daily.
Runs as a continuous loop (can be called from Celery task or standalone).
"""
import time
import logging
import requests
import json
from typing import Optional, Dict, Any
from datetime import datetime, date
from sqlalchemy import text
from apps.db.session import get_db_session

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
    """Fetch with exponential backoff on 429/5xx/timeouts"""
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
            
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                backoff = 2 ** attempt + 1
                logger.warning(f"trends_fetch_timeout url={url} attempt={attempt+1} backoff={backoff}s")
                time.sleep(backoff)
            else:
                logger.error(f"trends_fetch_timeout_failed url={url} after {max_retries} attempts")
                return None
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                backoff = 2 ** attempt + 1
                logger.warning(f"trends_fetch_error url={url} error={e} attempt={attempt+1} backoff={backoff}s")
                time.sleep(backoff)
            else:
                logger.error(f"trends_fetch_failed url={url} error={e} after {max_retries} attempts")
                return None
    
    return None


def _process_appdetails_job(db, job_id: int, steam_app_id: int) -> bool:
    """Process appdetails job: fetch and write to steam_app_facts"""
    logger.info(f"trends_job_pick job_id={job_id} job_type=appdetails steam_app_id={steam_app_id} attempts=1")
    
    try:
        # Update status to processing
        db.execute(
            text("UPDATE trend_jobs SET status='processing', updated_at=NOW() WHERE id=:job_id"),
            {"job_id": job_id}
        )
        db.commit()
        
        # Fetch appdetails
        url = "https://store.steampowered.com/api/appdetails"
        params = {"appids": steam_app_id, "cc": "us", "l": "en"}
        
        logger.info(f"trends_fetch_start job_type=appdetails steam_app_id={steam_app_id}")
        response = _fetch_with_backoff(url, params)
        
        if not response:
            raise Exception("Failed to fetch appdetails after retries")
        
        data = response.json()
        app_data = data.get(str(steam_app_id), {}).get("data")
        
        if not app_data or not app_data.get("success", False):
            raise Exception(f"Steam API returned no data or success=false for app {steam_app_id}")
        
        # Extract fields
        name = app_data.get("name", "")
        release_date_str = app_data.get("release_date", {}).get("date", "")
        release_date = None
        if release_date_str and release_date_str != "Coming soon":
            try:
                # Try parsing common formats
                for fmt in ["%d %b, %Y", "%b %d, %Y", "%Y-%m-%d"]:
                    try:
                        release_date = datetime.strptime(release_date_str, fmt).date()
                        break
                    except:
                        continue
            except:
                pass
        
        # Extract tags
        tags = []
        if "categories" in app_data:
            tags = [cat.get("description", "") for cat in app_data["categories"] if cat.get("description")]
        
        # Upsert steam_app_facts
        db.execute(
            text("""
                INSERT INTO steam_app_facts (steam_app_id, name, release_date, tags, updated_at)
                VALUES (:steam_app_id, :name, :release_date, :tags::jsonb, NOW())
                ON CONFLICT (steam_app_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    release_date = EXCLUDED.release_date,
                    tags = EXCLUDED.tags,
                    updated_at = EXCLUDED.updated_at
            """),
            {
                "steam_app_id": steam_app_id,
                "name": name,
                "release_date": release_date,
                "tags": json.dumps(tags)
            }
        )
        
        # Mark job as success
        db.execute(
            text("UPDATE trend_jobs SET status='success', updated_at=NOW() WHERE id=:job_id"),
            {"job_id": job_id}
        )
        db.commit()
        
        logger.info(f"trends_fetch_done job_type=appdetails steam_app_id={steam_app_id} result=success http_status={response.status_code}")
        return True
        
    except Exception as e:
        logger.error(f"trends_fetch_done job_type=appdetails steam_app_id={steam_app_id} result=failed error={e}", exc_info=True)
        db.rollback()
        
        # Increment attempts and retry if < max
        result = db.execute(
            text("""
                UPDATE trend_jobs 
                SET attempts = attempts + 1,
                    status = CASE WHEN attempts + 1 >= 3 THEN 'failed' ELSE 'queued' END,
                    updated_at = NOW()
                WHERE id = :job_id
                RETURNING attempts, status
            """),
            {"job_id": job_id}
        ).mappings().first()
        
        db.commit()
        
        if result and result["status"] == "queued":
            logger.info(f"trends_job_retry job_id={job_id} attempts={result['attempts']}")
        else:
            logger.error(f"trends_job_failed job_id={job_id} attempts={result['attempts'] if result else 'unknown'}")
        
        return False


def _process_reviews_daily_job(db, job_id: int, steam_app_id: int) -> bool:
    """Process reviews_daily job: fetch and write to steam_review_daily"""
    logger.info(f"trends_job_pick job_id={job_id} job_type=reviews_daily steam_app_id={steam_app_id} attempts=1")
    
    try:
        # Update status to processing
        db.execute(
            text("UPDATE trend_jobs SET status='processing', updated_at=NOW() WHERE id=:job_id"),
            {"job_id": job_id}
        )
        db.commit()
        
        # Fetch reviews summary (Steam Store API)
        url = f"https://store.steampowered.com/appreviews/{steam_app_id}"
        params = {
            "json": 1,
            "language": "all",
            "num_per_page": 0,  # We only need summary
            "purchase_type": "all"
        }
        
        logger.info(f"trends_fetch_start job_type=reviews_daily steam_app_id={steam_app_id}")
        response = _fetch_with_backoff(url, params)
        
        if not response:
            raise Exception("Failed to fetch reviews after retries")
        
        data = response.json()
        query_summary = data.get("query_summary", {})
        
        if not query_summary:
            raise Exception(f"Steam API returned no query_summary for app {steam_app_id}")
        
        # Extract review counts
        total_reviews = query_summary.get("total_reviews", 0)
        total_positive = query_summary.get("total_positive", 0)
        total_negative = query_summary.get("total_negative", 0)
        
        # Calculate percentages (as integers 0-100 for schema)
        positive_percent = None
        if total_reviews > 0:
            positive_percent = int(round((total_positive / total_reviews) * 100.0))
        
        # Recent reviews (30 days)
        recent_reviews = query_summary.get("reviews_written_in_past_30_days", 0)
        recent_positive = query_summary.get("recent_positive", 0)
        recent_negative = query_summary.get("recent_negative", 0)
        recent_positive_percent = None
        if recent_reviews > 0:
            recent_positive_percent = int(round((recent_positive / recent_reviews) * 100.0))
        
        today = date.today()
        
        # Upsert steam_review_daily (schema: all_reviews_count, all_positive_percent (int 0-100), recent_reviews_count_30d, recent_positive_percent_30d (int 0-100))
        db.execute(
            text("""
                INSERT INTO steam_review_daily (
                    steam_app_id, day,
                    all_reviews_count, all_positive_percent,
                    recent_reviews_count_30d, recent_positive_percent_30d,
                    computed_at
                )
                VALUES (
                    :steam_app_id, :day,
                    :all_reviews_count, :all_positive_percent,
                    :recent_reviews_count_30d, :recent_positive_percent_30d,
                    NOW()
                )
                ON CONFLICT (steam_app_id, day) DO UPDATE SET
                    all_reviews_count = EXCLUDED.all_reviews_count,
                    all_positive_percent = EXCLUDED.all_positive_percent,
                    recent_reviews_count_30d = EXCLUDED.recent_reviews_count_30d,
                    recent_positive_percent_30d = EXCLUDED.recent_positive_percent_30d,
                    computed_at = EXCLUDED.computed_at
            """),
            {
                "steam_app_id": steam_app_id,
                "day": today,
                "all_reviews_count": total_reviews,
                "all_positive_percent": positive_percent,
                "recent_reviews_count_30d": recent_reviews,
                "recent_positive_percent_30d": recent_positive_percent
            }
        )
        
        # Mark job as success
        db.execute(
            text("UPDATE trend_jobs SET status='success', updated_at=NOW() WHERE id=:job_id"),
            {"job_id": job_id}
        )
        db.commit()
        
        logger.info(f"trends_fetch_done job_type=reviews_daily steam_app_id={steam_app_id} result=success http_status={response.status_code} reviews={total_reviews}")
        return True
        
    except Exception as e:
        logger.error(f"trends_fetch_done job_type=reviews_daily steam_app_id={steam_app_id} result=failed error={e}", exc_info=True)
        db.rollback()
        
        # Increment attempts and retry if < max
        result = db.execute(
            text("""
                UPDATE trend_jobs 
                SET attempts = attempts + 1,
                    status = CASE WHEN attempts + 1 >= 3 THEN 'failed' ELSE 'queued' END,
                    updated_at = NOW()
                WHERE id = :job_id
                RETURNING attempts, status
            """),
            {"job_id": job_id}
        ).mappings().first()
        
        db.commit()
        
        if result and result["status"] == "queued":
            logger.info(f"trends_job_retry job_id={job_id} attempts={result['attempts']}")
        else:
            logger.error(f"trends_job_failed job_id={job_id} attempts={result['attempts'] if result else 'unknown'}")
        
        return False


def process_trend_jobs_once(db, limit: int = 10) -> Dict[str, Any]:
    """
    Process one batch of trend_jobs.
    Returns: {"processed": N, "success": M, "failed": K}
    """
    processed = 0
    success = 0
    failed = 0
    
    # Pick jobs with FOR UPDATE SKIP LOCKED (concurrency-safe)
    jobs = db.execute(
        text("""
            SELECT id, job_type, payload, attempts
            FROM trend_jobs
            WHERE status = 'queued'
              AND attempts < 3
            ORDER BY created_at ASC
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
        """),
        {"limit": limit}
    ).mappings().all()
    
    for job in jobs:
        job_id = job["id"]
        job_type = job["job_type"]
        payload = job["payload"]
        attempts = job["attempts"]
        
        try:
            steam_app_id = int(payload.get("steam_app_id"))
        except (ValueError, TypeError, AttributeError):
            logger.error(f"trends_job_invalid_payload job_id={job_id} payload={payload}")
            db.execute(
                text("UPDATE trend_jobs SET status='failed', updated_at=NOW() WHERE id=:job_id"),
                {"job_id": job_id}
            )
            db.commit()
            failed += 1
            continue
        
        processed += 1
        
        if job_type == "appdetails":
            if _process_appdetails_job(db, job_id, steam_app_id):
                success += 1
            else:
                failed += 1
        elif job_type == "reviews_daily":
            if _process_reviews_daily_job(db, job_id, steam_app_id):
                success += 1
            else:
                failed += 1
        else:
            logger.warning(f"trends_job_unknown_type job_id={job_id} job_type={job_type}")
            db.execute(
                text("UPDATE trend_jobs SET status='failed', updated_at=NOW() WHERE id=:job_id"),
                {"job_id": job_id}
            )
            db.commit()
            failed += 1
    
    return {"processed": processed, "success": success, "failed": failed}


def process_trend_jobs_loop(max_iterations: Optional[int] = None, sleep_seconds: float = 2.0):
    """
    Continuous loop to process trend_jobs.
    Stops when no jobs remain or max_iterations reached.
    """
    iteration = 0
    
    while True:
        if max_iterations and iteration >= max_iterations:
            break
        
        db = get_db_session()
        try:
            result = process_trend_jobs_once(db, limit=10)
            
            if result["processed"] == 0:
                logger.debug("trends_jobs_no_more_jobs")
                break
            
            logger.info(f"trends_jobs_batch processed={result['processed']} success={result['success']} failed={result['failed']}")
            
            iteration += 1
            time.sleep(sleep_seconds)
            
        except Exception as e:
            logger.error(f"trends_jobs_loop_error iteration={iteration} error={e}", exc_info=True)
        finally:
            db.close()
    
    logger.info(f"trends_jobs_loop_done iterations={iteration}")


if __name__ == "__main__":
    # Standalone runner
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    max_iter = None
    if len(sys.argv) > 1:
        max_iter = int(sys.argv[1])
    
    process_trend_jobs_loop(max_iterations=max_iter, sleep_seconds=2.0)
