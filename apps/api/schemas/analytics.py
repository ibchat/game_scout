"""
Analytics API Schemas
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class GameInvestmentScoreSchema(BaseModel):
    """Investment score для игры"""
    game_id: str
    game_title: str
    
    # Core scores
    product_potential: float
    gtm_execution: float
    gap_score: float
    fixability_score: float
    
    # External signals
    ewi_score: Optional[float] = None
    epv_score: Optional[float] = None
    
    # Classification
    investor_category: str
    investment_reasoning: Optional[str] = None
    
    # Metadata
    overall_confidence: float
    scored_at: datetime
    
    class Config:
        from_attributes = True


class DashboardStatsSchema(BaseModel):
    """Статистика для dashboard"""
    total_games: int
    games_scored: int
    
    # Category breakdown
    undermarketed_gems: int
    marketing_fixable: int
    product_risk: int
    not_investable: int
    watch: int
    
    # Average scores
    avg_product_potential: float
    avg_gtm_execution: float
    avg_gap_score: float
    
    # External signals stats
    games_with_ewi: int
    games_with_epv: int
    avg_ewi: Optional[float] = None
    avg_epv: Optional[float] = None


class EnrichedGameSchema(BaseModel):
    """Игра с полным набором analytics данных"""
    # Basic info
    game_id: str
    title: str
    source: str
    url: str
    description: Optional[str] = None
    
    # Investment scores
    scores: Optional[GameInvestmentScoreSchema] = None
    
    # External signals summary
    external_signals: Optional[Dict[str, Any]] = None
    
    # Metrics
    latest_metrics: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True
