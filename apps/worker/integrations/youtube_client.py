import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class YouTubeClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
    
    def search_videos(self, query, max_results=25):
        if not self.api_key:
            logger.warning("No YouTube API key, using mock data")
            return self._generate_mock_data(query, max_results)
        
        try:
            from googleapiclient.discovery import build
            youtube = build('youtube', 'v3', developerKey=self.api_key)
            
            request = youtube.search().list(
                part='snippet',
                q=query,
                type='video',
                maxResults=max_results,
                order='viewCount',
                relevanceLanguage='en'
            )
            response = request.execute()
            
            videos = []
            for item in response.get('items', []):
                video_id = item['id']['videoId']
                videos.append({
                    'video_id': video_id,
                    'title': item['snippet']['title'],
                    'url': f"https://www.youtube.com/watch?v={video_id}",  # FIX!
                    'channel_title': item['snippet']['channelTitle'],
                    'published_at': item['snippet']['publishedAt'],
                    'view_count': 0,
                    'like_count': 0,
                    'comment_count': 0
                })
            
            return videos
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return self._generate_mock_data(query, max_results)
    
    def _generate_mock_data(self, query, max_results):
        import random
        videos = []
        for i in range(min(max_results, 15)):
            video_id = f"mock_{i}_{random.randint(1000, 9999)}"
            videos.append({
                'video_id': video_id,
                'title': f"Mock: {query} #{i+1}",
                'url': f"https://www.youtube.com/watch?v={video_id}",  # FIX!
                'channel_title': f"Channel{i}",
                'published_at': datetime.utcnow().isoformat() + 'Z',
                'view_count': random.randint(1000, 100000),
                'like_count': random.randint(100, 10000),
                'comment_count': random.randint(10, 1000)
            })
        return videos
