"""
Base collector for Intel module.
Provides common functionality: retry/backoff, policy validation, idempotency.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

from apps.intel.policy.policy_engine import validate_source_url
from apps.intel.db.models import IntelSource, IntelRawItem
from apps.worker.collectors.http_client import http_client

logger = logging.getLogger(__name__)


class BaseIntelCollector:
    """Base class for Intel collectors with common functionality."""
    
    def __init__(self):
        self.http_client = http_client
    
    def validate_url(self, url: str) -> tuple[bool, str]:
        """
        Validate URL against policy.
        Returns: (is_allowed, reason)
        """
        decision, reason = validate_source_url(url)
        return decision == "allow", reason
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True
    )
    def fetch_url(self, url: str, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
        """
        Fetch URL with retry/backoff.
        """
        return self.http_client.get(url, headers=headers)
    
    def save_raw_item(
        self,
        db: Session,
        source: IntelSource,
        url: str,
        title: str,
        snippet: Optional[str] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
        raw_html: Optional[str] = None
    ) -> Optional[IntelRawItem]:
        """
        Save raw item to database with idempotency (UNIQUE url constraint).
        Returns: IntelRawItem if saved, None if duplicate or error.
        """
        # Validate URL first
        is_allowed, reason = self.validate_url(url)
        if not is_allowed:
            logger.debug(f"URL rejected by policy: {url} - {reason}")
            return None
        
        try:
            raw_item = IntelRawItem(
                source_id=source.id,
                fetched_at=datetime.utcnow(),
                url=url,
                title=title,
                snippet=snippet,
                raw_payload=raw_payload,
                raw_html=raw_html
            )
            
            db.add(raw_item)
            db.commit()
            db.refresh(raw_item)
            
            logger.debug(f"Saved raw item: {url[:80]}...")
            return raw_item
            
        except IntegrityError:
            # Duplicate URL (idempotency)
            db.rollback()
            logger.debug(f"Duplicate URL (skipped): {url[:80]}...")
            return None
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save raw item {url}: {e}", exc_info=True)
            return None
    
    def collect(self, db: Session, source: IntelSource) -> Dict[str, int]:
        """
        Collect items from source.
        Must be implemented by subclasses.
        Returns: {collected: int, saved: int, errors: int}
        """
        raise NotImplementedError("Subclasses must implement collect()")
