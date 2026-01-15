from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID


class PitchCreate(BaseModel):
    dev_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    studio_name: Optional[str] = Field(None, max_length=255)
    team_size: int = Field(..., ge=1, le=1000)
    released_before: bool
    timeline_months: int = Field(..., ge=1, le=120)
    pitch_text: str = Field(..., min_length=10)
    hook_one_liner: Optional[str] = Field(None, max_length=500)
    links: dict = Field(default_factory=dict)
    build_link: Optional[str] = Field(None, max_length=1000)
    video_link: Optional[str] = Field(None, max_length=1000)
    tags: list[str] = Field(default_factory=list)


class PitchScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pitch_id: UUID
    
    # === LEGACY FIELDS (сохраняем для обратной совместимости) ===
    score_total: Optional[int] = None  # Может быть None если используется новый scoring
    score_hook: Optional[int] = None
    score_market: Optional[int] = None
    score_team: Optional[int] = None
    score_steam: Optional[int] = None
    score_asymmetry: Optional[int] = None
    verdict: str
    why_yes: Optional[list[str]] = None
    why_no: Optional[list[str]] = None
    next_step: Optional[str] = None
    comparables: Optional[list[dict]] = None
    
    # === NEW: INVESTOR SCORING FIELDS ===
    # Legacy compatibility score
    score: Optional[float] = None
    
    # Investor layers
    product_potential: Optional[float] = None
    product_confidence: Optional[str] = None
    gtm_execution: Optional[float] = None
    gtm_confidence: Optional[str] = None
    team_delivery: Optional[float] = None
    team_confidence: Optional[str] = None
    
    # Key metrics
    potential_gap: Optional[float] = None
    fixability_score: Optional[float] = None
    investment_profile: Optional[str] = None
    
    # Explanations (new structure)
    explanation: Optional[dict] = None
    breakdown: Optional[dict] = None
    
    created_at: datetime


class PitchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dev_name: str
    email: str
    studio_name: Optional[str]
    team_size: int
    released_before: bool
    timeline_months: int
    pitch_text: str
    hook_one_liner: Optional[str]
    links: dict
    build_link: Optional[str]
    video_link: Optional[str]
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    
    # Legacy score field (deprecated but kept for compatibility)
    score: Optional[float] = None
    
    # Full score object (can be None if not scored yet)
    pitch_scores: Optional[list[PitchScoreResponse]] = None


class PitchListResponse(BaseModel):
    pitches: list[PitchResponse]
    total: int
    page: int
    page_size: int


class InvestorBreakdownResponse(BaseModel):
    """Detailed investor scoring breakdown"""
    pitch_id: UUID
    pitch_title: str
    
    # Investor layers
    product_potential: float
    product_confidence: str
    gtm_execution: float
    gtm_confidence: str
    team_delivery: float
    team_confidence: str
    
    # Key metrics
    potential_gap: float
    fixability_score: float
    investment_profile: str
    
    # Explanations
    explanation: dict
    breakdown: dict
    
    # Legacy
    legacy_score: float
    legacy_verdict: str