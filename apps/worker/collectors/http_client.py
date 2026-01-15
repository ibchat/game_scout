import httpx
import time
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import os

logger = logging.getLogger(__name__)


class RateLimitedHTTPClient:
    """HTTP client with rate limiting and retries"""
    
    def __init__(self):
        self.rate_limit = float(os.getenv("SCRAPE_RATE_LIMIT_PER_HOST", "1"))
        self.timeout = int(os.getenv("SCRAPE_TIMEOUT_SECONDS", "20"))
        self.user_agent = os.getenv("USER_AGENT", "GameScoutBot/1.0")
        self.last_request_time = {}
        
    def _wait_for_rate_limit(self, host: str):
        """Wait to respect rate limit for host"""
        now = time.time()
        last_time = self.last_request_time.get(host, 0)
        elapsed = now - last_time
        
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {host}")
            time.sleep(sleep_time)
        
        self.last_request_time[host] = time.time()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def get(self, url: str, headers: Optional[dict] = None) -> httpx.Response:
        """Make GET request with rate limiting and retries"""
        # Extract host for rate limiting
        parsed = httpx.URL(url)
        host = parsed.host
        
        # Wait for rate limit
        self._wait_for_rate_limit(host)
        
        # Prepare headers
        req_headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        if headers:
            req_headers.update(headers)
        
        # Make request
        logger.info(f"GET {url}")
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(url, headers=req_headers)
                response.raise_for_status()
                return response
        except httpx.HTTPError as e:
            logger.error(f"HTTP error for {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")
            raise


# Global client instance
http_client = RateLimitedHTTPClient()