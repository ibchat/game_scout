from pydantic import BaseModel, ConfigDict
from datetime import date
from uuid import UUID


class TrendResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    date: date
    signal: str
    signal_type: str
    count: int
    avg_7d: float
    delta_7d: float
    velocity: float


class TrendListResponse(BaseModel):
    trends: list[TrendResponse]
    total: int