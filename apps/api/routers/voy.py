"""
VOY (Voyager-style Scout) API Router
Read-only overlay for game scouting with learning capabilities
"""
import logging
import os
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session

from apps.api.deps import get_db_session
from apps.api.schemas.voy import (
    VoySkillCreate,
    VoySkillResponse,
    VoyRunCreate,
    VoyRunResponse,
    VoyRunItemResponse,
    VoyRunWithItemsResponse,
    VoyFeedbackCreate,
    VoyFeedbackResponse,
    VoyLearningConfigResponse,
    VoyLearningConfigUpdate,
    VoyLearningLogResponse,
    VoyMethodologyResponse,
    VoyOverrideCreate,
    VoyOverrideResponse
)
from apps.api.services.voy_engine import VoyEngine

logger = logging.getLogger(__name__)

# Import VOY models from voy_engine to use the same instances (avoids duplicate Base registration)
try:
    from apps.api.services.voy_engine import (
        VoySkill, VoyRun, VoyRunItem, VoyFeedback,
        VoyLearningConfig, VoyLearningLog, VoyMethodology, VoyOverride
    )
    logger.info("✅ Loaded VOY models from voy_engine")
except ImportError as e:
    logger.error(f"❌ Failed to import VOY models from voy_engine: {e}", exc_info=True)
    # Create dummy classes to allow router to load (but endpoints will fail)
    class VoySkill: pass
    class VoyRun: pass
    class VoyRunItem: pass
    class VoyFeedback: pass
    class VoyLearningConfig: pass
    class VoyLearningLog: pass
    class VoyMethodology: pass
    class VoyOverride: pass
    logger.warning("⚠️ Using dummy VOY model classes - endpoints will not work")

router = APIRouter(prefix="/voy", tags=["VOY"])

# Feature flag
VOY_ENABLED = os.getenv("VOY_ENABLED", "false").lower() == "true"


def check_voy_enabled():
    """Check if VOY is enabled"""
    if not VOY_ENABLED:
        raise HTTPException(status_code=403, detail="VOY module is disabled. Set VOY_ENABLED=true to enable.")


@router.get("/health")
async def voy_health() -> Dict[str, Any]:
    """Health check for VOY module - always available, no check_voy_enabled()"""
    return {
        "status": "ok",
        "module": "voy",
        "enabled": VOY_ENABLED,
        "message": "VOY module is available" if VOY_ENABLED else "VOY module is disabled. Set VOY_ENABLED=true to enable."
    }


@router.get("/skills", response_model=List[VoySkillResponse])
async def list_skills(
    goal: Optional[str] = Query(None, description="Filter by goal"),
    db: Session = Depends(get_db_session),
) -> List[VoySkillResponse]:
    """List all skills (optionally filtered by goal)"""
    check_voy_enabled()
    
    engine = VoyEngine(db)
    skills = engine.get_skills_for_goal(goal)
    return [VoySkillResponse.model_validate(skill) for skill in skills]


@router.post("/skills", response_model=VoySkillResponse)
async def create_skill(
    skill_data: VoySkillCreate,
    db: Session = Depends(get_db_session),
) -> VoySkillResponse:
    """Create a new skill"""
    check_voy_enabled()
    
    # Clamp weight to [0.2, 3.0]
    weight = max(0.2, min(3.0, skill_data.weight))
    
    skill = VoySkill(
        name=skill_data.name,
        description=skill_data.description,
        weight=weight,
        goal=skill_data.goal
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    
    return VoySkillResponse.model_validate(skill)


@router.post("/runs", response_model=VoyRunResponse)
async def create_run(
    run_data: VoyRunCreate,
    db: Session = Depends(get_db_session),
) -> VoyRunResponse:
    """Create a new VOY run"""
    check_voy_enabled()
    
    engine = VoyEngine(db)
    run = engine.create_run(run_data.goal)
    return VoyRunResponse.model_validate(run)


@router.post("/runs/{run_id}/execute", response_model=VoyRunResponse)
async def execute_run(
    run_id: UUID,
    shortlist_size: int = Query(10, ge=1, le=50, description="Number of items in shortlist"),
    db: Session = Depends(get_db_session),
) -> VoyRunResponse:
    """Execute a VOY run (fetch candidates, score, create shortlist)"""
    check_voy_enabled()
    
    engine = VoyEngine(db)
    run = engine.execute_run(run_id, shortlist_size)
    return VoyRunResponse.model_validate(run)


@router.get("/runs/{run_id}", response_model=VoyRunWithItemsResponse)
async def get_run(
    run_id: UUID,
    db: Session = Depends(get_db_session),
) -> VoyRunWithItemsResponse:
    """Get a run with its items"""
    check_voy_enabled()
    
    run = db.query(VoyRun).filter(VoyRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    items = db.query(VoyRunItem).filter(VoyRunItem.run_id == run_id).order_by(VoyRunItem.rank).all()
    
    return VoyRunWithItemsResponse(
        run=VoyRunResponse.model_validate(run),
        items=[VoyRunItemResponse.model_validate(item) for item in items]
    )


@router.get("/runs", response_model=List[VoyRunResponse])
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> List[VoyRunResponse]:
    """List recent runs"""
    check_voy_enabled()
    
    runs = db.query(VoyRun).order_by(VoyRun.created_at.desc()).limit(limit).all()
    return [VoyRunResponse.model_validate(run) for run in runs]


@router.post("/feedback", response_model=VoyFeedbackResponse)
async def create_feedback(
    feedback_data: VoyFeedbackCreate,
    db: Session = Depends(get_db_session),
) -> VoyFeedbackResponse:
    """Submit feedback on a run item (updates skill weights)"""
    check_voy_enabled()
    
    if feedback_data.feedback_type not in ["good", "bad"]:
        raise HTTPException(status_code=400, detail="feedback_type must be 'good' or 'bad'")
    
    engine = VoyEngine(db)
    feedback = engine.process_feedback(
        feedback_data.run_item_id,
        feedback_data.feedback_type,
        feedback_data.notes
    )
    
    return VoyFeedbackResponse.model_validate(feedback)


@router.get("/learning-config", response_model=VoyLearningConfigResponse)
async def get_learning_config(
    db: Session = Depends(get_db_session),
) -> VoyLearningConfigResponse:
    """Get learning configuration"""
    check_voy_enabled()
    
    engine = VoyEngine(db)
    config = engine.get_learning_config()
    
    # Convert frozen_skills JSONB to list
    frozen_skills = config.frozen_skills
    if isinstance(frozen_skills, str):
        import json
        try:
            frozen_skills = json.loads(frozen_skills)
        except:
            frozen_skills = []
    if not isinstance(frozen_skills, list):
        frozen_skills = []
    
    return VoyLearningConfigResponse(
        id=config.id,
        learning_enabled=config.learning_enabled,
        learning_rate=config.learning_rate,
        max_weight_delta=config.max_weight_delta,
        min_skill_weight=config.min_skill_weight,
        max_skill_weight=config.max_skill_weight,
        min_feedback_count=config.min_feedback_count,
        frozen_skills=frozen_skills,
        allow_gpt_advice=config.allow_gpt_advice,
        created_at=config.created_at,
        updated_at=config.updated_at
    )


@router.patch("/learning-config", response_model=VoyLearningConfigResponse)
async def update_learning_config(
    config_update: VoyLearningConfigUpdate,
    db: Session = Depends(get_db_session),
) -> VoyLearningConfigResponse:
    """Update learning configuration"""
    check_voy_enabled()
    
    engine = VoyEngine(db)
    config = engine.get_learning_config()
    
    # Update fields
    if config_update.learning_enabled is not None:
        config.learning_enabled = config_update.learning_enabled
    if config_update.learning_rate is not None:
        config.learning_rate = config_update.learning_rate
    if config_update.max_weight_delta is not None:
        config.max_weight_delta = config_update.max_weight_delta
    if config_update.min_skill_weight is not None:
        config.min_skill_weight = config_update.min_skill_weight
    if config_update.max_skill_weight is not None:
        config.max_skill_weight = config_update.max_skill_weight
    if config_update.min_feedback_count is not None:
        config.min_feedback_count = config_update.min_feedback_count
    if config_update.frozen_skills is not None:
        config.frozen_skills = config_update.frozen_skills
    if config_update.allow_gpt_advice is not None:
        config.allow_gpt_advice = config_update.allow_gpt_advice
    
    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    
    # Convert frozen_skills to list
    frozen_skills = config.frozen_skills
    if isinstance(frozen_skills, str):
        import json
        try:
            frozen_skills = json.loads(frozen_skills)
        except:
            frozen_skills = []
    if not isinstance(frozen_skills, list):
        frozen_skills = []
    
    return VoyLearningConfigResponse(
        id=config.id,
        learning_enabled=config.learning_enabled,
        learning_rate=config.learning_rate,
        max_weight_delta=config.max_weight_delta,
        min_skill_weight=config.min_skill_weight,
        max_skill_weight=config.max_skill_weight,
        min_feedback_count=config.min_feedback_count,
        frozen_skills=frozen_skills,
        allow_gpt_advice=config.allow_gpt_advice,
        created_at=config.created_at,
        updated_at=config.updated_at
    )


@router.get("/learning-log", response_model=List[VoyLearningLogResponse])
async def get_learning_log(
    limit: int = Query(50, ge=1, le=500),
    skill_key: Optional[str] = Query(None, description="Filter by skill key"),
    source: Optional[str] = Query(None, description="Filter by source: 'feedback' or 'gpt_advice'"),
    db: Session = Depends(get_db_session),
) -> List[VoyLearningLogResponse]:
    """Get learning log entries"""
    check_voy_enabled()
    
    query = db.query(VoyLearningLog)
    
    if skill_key:
        query = query.filter(VoyLearningLog.skill_key == skill_key)
    if source:
        query = query.filter(VoyLearningLog.source == source)
    
    logs = query.order_by(VoyLearningLog.created_at.desc()).limit(limit).all()
    
    return [VoyLearningLogResponse.model_validate(log) for log in logs]


@router.get("/methodology", response_model=VoyMethodologyResponse)
async def get_methodology(
    db: Session = Depends(get_db_session),
) -> VoyMethodologyResponse:
    """Get Bonfire Methodology (read-only normative document)"""
    check_voy_enabled()
    
    methodology = db.query(VoyMethodology).filter(
        VoyMethodology.is_active == True
    ).order_by(VoyMethodology.created_at.desc()).first()
    
    if not methodology:
        raise HTTPException(status_code=404, detail="Methodology not found")
    
    return VoyMethodologyResponse.model_validate(methodology)


@router.post("/override", response_model=VoyOverrideResponse)
async def create_override(
    override_data: VoyOverrideCreate,
    db: Session = Depends(get_db_session),
) -> VoyOverrideResponse:
    """Record user override (when investor overrides system decision)"""
    check_voy_enabled()
    
    # Verify run_item exists
    run_item = db.query(VoyRunItem).filter(VoyRunItem.id == override_data.run_item_id).first()
    if not run_item:
        raise HTTPException(status_code=404, detail="Run item not found")
    
    # Create override record
    override = VoyOverride(
        run_item_id=override_data.run_item_id,
        system_recommendation=override_data.system_recommendation,
        user_decision=override_data.user_decision,
        reason=override_data.reason
    )
    db.add(override)
    db.commit()
    db.refresh(override)
    
    logger.info(f"Override recorded: run_item_id={override_data.run_item_id}, decision={override_data.user_decision}")
    
    return VoyOverrideResponse.model_validate(override)


@router.get("/overrides", response_model=List[VoyOverrideResponse])
async def get_overrides(
    run_item_id: Optional[UUID] = Query(None, description="Filter by run item ID"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> List[VoyOverrideResponse]:
    """Get override records"""
    check_voy_enabled()
    
    query = db.query(VoyOverride)
    
    if run_item_id:
        query = query.filter(VoyOverride.run_item_id == run_item_id)
    
    overrides = query.order_by(VoyOverride.created_at.desc()).limit(limit).all()
    
    return [VoyOverrideResponse.model_validate(override) for override in overrides]
