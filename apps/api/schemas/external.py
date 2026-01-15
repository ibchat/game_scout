"""
External Signals Schemas
"""
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime


class ExternalVideoSchema(BaseModel):
    """External video (YouTube/TikTok)"""
    video_id: str
    platform: str
    title: Optional[str]
    url: str
    views: Optional[int]
    likes: Optional[int]
    comments_count: Optional[int]
    published_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ExternalSignalSchema(BaseModel):
    """Aggregated external signal"""
    game_id: str
    date: datetime
    
    youtube_signal: Optional[Dict] = None
    tiktok_signal: Optional[Dict] = None
    
    epv_score: float
    epv_confidence: float
    
    videos_analyzed: int
    comments_analyzed: int
    
    class Config:
        from_attributes = True
