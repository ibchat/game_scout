from pydantic import BaseModel, ConfigDict, model_validator
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID

class GameResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    source: str
    source_id: str
    title: Optional[str] = None
    url: str
    description: Optional[str] = None
    tags: List[str] = []
    price_eur: Optional[float] = None
    has_demo: bool = False
    release_status: str
    created_at: datetime
    updated_at: datetime
    metrics: List["GameMetricsResponse"] = []


    @model_validator(mode='after')
    def sort_metrics_by_date(self):
        """Sort metrics by date descending (newest first)"""
        if self.metrics:
            self.metrics = sorted(self.metrics, key=lambda m: m.date, reverse=True)
        return self

class GameMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    game_id: UUID
    date: datetime
    reviews_total: Optional[int] = None
    reviews_7d: Optional[int] = None
    reviews_30d: Optional[int] = None
    review_velocity_7d: Optional[float] = None
    momentum_ratio: Optional[float] = None
    followers: Optional[int] = None
    wishlists: Optional[int] = None
    created_at: datetime

class GameListResponse(BaseModel):
    games: List[GameResponse]
    total: int
    page: int
    page_size: int
