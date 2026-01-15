import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TikTokClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.base_url = "https://open.tiktokapis.com/v2"
    
    def search_videos(self, query, max_results=25, days_back=30):
        """
        Search TikTok videos via Research API
        https://developers.tiktok.com/doc/research-api-specs-query-videos
        """
        if not self.api_key:
            logger.warning("No TikTok API key, returning mock data")
            return self._generate_mock_data(query, max_results)
        
        try:
            start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime('%Y%m%d')
            end_date = datetime.utcnow().strftime('%Y%m%d')
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "query": {
                    "and": [
                        {"field_name": "keyword", "operation": "IN", "field_values": [query]},
                        {"field_name": "region_code", "operation": "IN", "field_values": ["US", "GB", "RU"]}
                    ]
                },
                "start_date": start_date,
                "end_date": end_date,
                "max_count": max_results
            }
            
            response = requests.post(
                f"{self.base_url}/research/video/query/",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"TikTok API error: {response.status_code} {response.text}")
                return self._generate_mock_data(query, max_results)
            
            data = response.json()
            videos = []
            
            for video in data.get('data', {}).get('videos', []):
                videos.append({
                    'video_id': video.get('id'),
                    'title': video.get('video_description', '')[:200],
                    'url': f"https://www.tiktok.com/@{video.get('username')}/video/{video.get('id')}",
                    'username': video.get('username'),
                    'view_count': video.get('view_count', 0),
                    'like_count': video.get('like_count', 0),
                    'comment_count': video.get('comment_count', 0),
                    'share_count': video.get('share_count', 0),
                    'created_at': video.get('create_time')
                })
            
            logger.info(f"Found {len(videos)} TikTok videos for query: {query}")
            return videos
            
        except Exception as e:
            logger.error(f"TikTok search error: {e}", exc_info=True)
            return self._generate_mock_data(query, max_results)
    
    def _generate_mock_data(self, query, max_results):
        """Generate mock TikTok data for testing"""
        import random
        videos = []
        for i in range(min(max_results, 15)):
            videos.append({
                'video_id': f"mock_tiktok_{i}_{random.randint(1000, 9999)}",
                'title': f"Mock TikTok: {query} #{i+1}",
                'url': f"https://www.tiktok.com/@gamer{i}/video/mock{i}",
                'username': f"gamer{i}",
                'view_count': random.randint(50000, 500000),
                'like_count': random.randint(5000, 50000),
                'comment_count': random.randint(100, 1000),
                'share_count': random.randint(50, 500),
                'created_at': datetime.utcnow().isoformat()
            })
        return videos
