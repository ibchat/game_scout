"""
VOY (Voyager-style Scout) API Schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class VoySkillCreate(BaseModel):
    """Create a new skill"""
    name: str = Field(..., description="Skill name")
    description: Optional[str] = Field(None, description="Skill description")
    weight: float = Field(1.0, ge=0.2, le=3.0, description="Skill weight (clamped to [0.2, 3.0])")
    goal: Optional[str] = Field(None, description="Optional goal this skill is optimized for")


class VoySkillResponse(BaseModel):
    """Skill response"""
    id: UUID
    name: str
    description: Optional[str]
    weight: float
    goal: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VoyRunCreate(BaseModel):
    """Create a new VOY run"""
    goal: str = Field(..., description="Goal description for this run")


class VoyRunResponse(BaseModel):
    """Run response"""
    id: UUID
    goal: str
    status: str
    total_candidates: int
    shortlist_size: int
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class VoyRunItemResponse(BaseModel):
    """Run item response"""
    id: UUID
    run_id: UUID
    game_id: UUID
    app_id: Optional[int]
    title: Optional[str]
    total_score: float
    explanation: Optional[str]
    features_json: Optional[Dict[str, Any]]
    skill_scores_json: Optional[Dict[str, Any]]
    rank: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class VoyRunWithItemsResponse(BaseModel):
    """Run with items"""
    run: VoyRunResponse
    items: List[VoyRunItemResponse]


class VoyFeedbackCreate(BaseModel):
    """Create feedback"""
    run_item_id: UUID = Field(..., description="Run item ID")
    feedback_type: str = Field(..., description="Feedback type: 'good' or 'bad'")
    notes: Optional[str] = Field(None, description="Optional notes")


class VoyFeedbackResponse(BaseModel):
    """Feedback response"""
    id: UUID
    run_item_id: UUID
    feedback_type: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class VoyLearningConfigResponse(BaseModel):
    """Learning config response"""
    id: UUID
    learning_enabled: bool
    learning_rate: float
    max_weight_delta: float
    min_skill_weight: float
    max_skill_weight: float
    min_feedback_count: int
    frozen_skills: List[str]
    allow_gpt_advice: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VoyLearningConfigUpdate(BaseModel):
    """Update learning config"""
    learning_enabled: Optional[bool] = None
    learning_rate: Optional[float] = Field(None, ge=0.01, le=0.5)
    max_weight_delta: Optional[float] = Field(None, ge=0.01, le=0.5)
    min_skill_weight: Optional[float] = Field(None, ge=0.1, le=1.0)
    max_skill_weight: Optional[float] = Field(None, ge=1.0, le=5.0)
    min_feedback_count: Optional[int] = Field(None, ge=1, le=100)
    frozen_skills: Optional[List[str]] = None
    allow_gpt_advice: Optional[bool] = None


class VoyLearningLogResponse(BaseModel):
    """Learning log response"""
    id: UUID
    run_item_id: UUID
    skill_key: str
    old_weight: float
    new_weight: float
    delta: float
    reason: Optional[str]
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class VoyMethodologyResponse(BaseModel):
    """Methodology response (read-only)"""
    id: UUID
    version: str
    title: str
    content_text: str
    content_json: Dict[str, Any]
    is_active: bool
    is_readonly: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VoyOverrideCreate(BaseModel):
    """Create override record"""
    run_item_id: UUID
    system_recommendation: str
    user_decision: str
    reason: Optional[str] = None


class VoyOverrideResponse(BaseModel):
    """Override response"""
    id: UUID
    run_item_id: UUID
    system_recommendation: str
    user_decision: str
    reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
