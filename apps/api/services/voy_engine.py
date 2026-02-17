"""
VOY Engine - Core logic for Voyager-style Scout
"""
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import json

logger = logging.getLogger(__name__)

# Import VOY models - try multiple import methods
try:
    # Method 1: Try direct file import (for Docker)
    import importlib.util
    import os
    import sys
    from pathlib import Path
    
    voy_models = None
    # Calculate correct paths - __file__ is /app/apps/api/services/voy_engine.py
    # So parent.parent.parent = /app/apps
    current_file = Path(__file__)
    app_root = current_file.parent.parent.parent  # /app/apps
    voy_file_path = app_root / "db" / "models" / "voy.py"  # /app/apps/db/models/voy.py
    
    base_paths = [
        voy_file_path,  # Calculated path (primary)
        Path("/app/apps/db/models/voy.py"),  # Docker absolute path
    ]
    
    for voy_path in base_paths:
        try:
            if voy_path.exists():
                logger.info(f"Attempting to load VOY models from {voy_path}")
                
                # Add necessary paths to sys.path for imports to work
                app_root = Path("/app") if Path("/app").exists() else Path(__file__).parent.parent.parent
                if str(app_root) not in sys.path:
                    sys.path.insert(0, str(app_root))
                
                # Import Base first - use the same Base instance
                from apps.db.base import Base as VoyBase
                
                # Use importlib to load the module properly
                # Use a consistent module name to avoid duplicate registrations
                module_name = "apps.db.models.voy"
                
                # Check if VOY classes are already registered in Base registry
                voy_classes_registered = any(
                    'VoySkill' in str(cls) or 'VoyRun' in str(cls) 
                    for cls in VoyBase.registry._class_registry.values()
                )
                
                if voy_classes_registered:
                    logger.info(f"✅ VOY classes already registered in Base registry, skipping reload")
                    # Find the classes in the registry
                    for cls in VoyBase.registry._class_registry.values():
                        if hasattr(cls, '__name__') and cls.__name__.startswith('Voy'):
                            if cls.__name__ == 'VoySkill':
                                VoySkill = cls
                            elif cls.__name__ == 'VoyRun':
                                VoyRun = cls
                            elif cls.__name__ == 'VoyRunItem':
                                VoyRunItem = cls
                            elif cls.__name__ == 'VoyFeedback':
                                VoyFeedback = cls
                            elif cls.__name__ == 'VoyLearningConfig':
                                VoyLearningConfig = cls
                            elif cls.__name__ == 'VoyLearningLog':
                                VoyLearningLog = cls
                            elif cls.__name__ == 'VoyMethodology':
                                VoyMethodology = cls
                            elif cls.__name__ == 'VoyOverride':
                                VoyOverride = cls
                    logger.info(f"✅ Found VOY classes in registry")
                    voy_models = True
                    break
                
                # Check if module already loaded
                if module_name in sys.modules:
                    voy_module = sys.modules[module_name]
                    if hasattr(voy_module, 'VoySkill'):
                        logger.info(f"✅ Using already loaded module: {module_name}")
                    else:
                        logger.warning(f"Module {module_name} cached but incomplete, reloading...")
                        del sys.modules[module_name]
                        voy_module = None
                else:
                    voy_module = None
                
                if voy_module is None:
                    spec = importlib.util.spec_from_file_location(module_name, voy_path)
                    voy_module = importlib.util.module_from_spec(spec)
                    
                    # Add necessary imports to module's namespace before execution
                    import sqlalchemy as sa
                    from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
                    import uuid as uuid_module
                    
                    # Set up module namespace with imports - use the same Base instance
                    voy_module.Base = VoyBase  # Use the same Base instance
                    voy_module.Column = sa.Column
                    voy_module.String = sa.String
                    voy_module.Integer = sa.Integer
                    voy_module.Float = sa.Float
                    voy_module.Text = sa.Text
                    voy_module.ForeignKey = sa.ForeignKey
                    voy_module.DateTime = sa.DateTime
                    voy_module.JSON = sa.JSON
                    voy_module.Boolean = sa.Boolean
                    voy_module.UUID = PG_UUID
                    voy_module.JSONB = JSONB
                    voy_module.relationship = sa.orm.relationship
                    voy_module.func = sa.sql.func
                    voy_module.uuid = uuid_module
                    voy_module.sa = sa
                    
                    # Execute the module and cache it
                    spec.loader.exec_module(voy_module)
                    sys.modules[module_name] = voy_module  # Cache the module
                    logger.info(f"✅ Successfully loaded and cached voy.py module: {module_name}")
                
                # Extract classes from module
                if hasattr(voy_module, 'VoySkill'):
                    VoySkill = voy_module.VoySkill
                    VoyRun = voy_module.VoyRun
                    VoyRunItem = voy_module.VoyRunItem
                    VoyFeedback = voy_module.VoyFeedback
                    VoyLearningConfig = voy_module.VoyLearningConfig
                    VoyLearningLog = voy_module.VoyLearningLog
                    VoyMethodology = voy_module.VoyMethodology
                    VoyOverride = voy_module.VoyOverride
                    logger.info(f"✅ Loaded VOY models from {voy_path}")
                    voy_models = True  # Mark as loaded
                    break
                else:
                    logger.warning(f"VOY models file found but VoySkill not found. Available: {dir(voy_module)[:20]}")
        except Exception as path_error:
            logger.error(f"Failed to load from {voy_path}: {path_error}", exc_info=True)
            continue
    
    if not voy_models:
        raise ImportError(f"Failed to load VOY models from any path. Tried: {base_paths}")
except ImportError as import_err:
    logger.error(f"❌ Failed to import VOY models: {import_err}", exc_info=True)
    raise  # Re-raise to prevent silent failures
except Exception as e:
    logger.error(f"❌ Unexpected error importing VOY models: {e}", exc_info=True)
    raise  # Re-raise unexpected errors

# Export models for use in other modules (e.g., voy router)
__all__ = ['VoySkill', 'VoyRun', 'VoyRunItem', 'VoyFeedback', 
           'VoyLearningConfig', 'VoyLearningLog', 'VoyMethodology', 'VoyOverride']
from apps.api.services.voy_gpt import VoyGPTService

logger = logging.getLogger(__name__)


class VoyEngine:
    """VOY Engine for scoring and learning"""
    
    def __init__(self, db: Session):
        self.db = db
        self._gpt_service = VoyGPTService()
    
    def get_learning_config(self) -> VoyLearningConfig:
        """Get learning config (create default if not exists)"""
        config = self.db.query(VoyLearningConfig).first()
        if not config:
            config = VoyLearningConfig()
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config
    
    def get_skills_for_goal(self, goal: Optional[str] = None) -> List[VoySkill]:
        """Get skills for a goal (or all skills if goal is None)"""
        query = self.db.query(VoySkill)
        if goal:
            query = query.filter(
                (VoySkill.goal == goal) | (VoySkill.goal.is_(None))
            )
        return query.all()
    
    def fetch_candidates(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch candidate games from existing signals (read-only).
        Uses deal_intent_signal as source.
        """
        # Get unique games with signals
        query = text("""
            SELECT DISTINCT ON (app_id)
                app_id,
                MAX(created_at) as latest_signal_at,
                COUNT(*) as signal_count,
                MAX(publisher_intent_score) as max_intent_score,
                MAX(confidence) as max_confidence
            FROM deal_intent_signal
            WHERE app_id IS NOT NULL
            GROUP BY app_id
            ORDER BY app_id, latest_signal_at DESC
            LIMIT :limit
        """)
        
        rows = self.db.execute(query, {"limit": limit}).mappings().all()
        
        candidates = []
        for row in rows:
            # Generate game_id (UUID) for VOY logic
            # In real implementation, this would map to actual game_id from games table
            # For now, we use a deterministic UUID based on app_id
            game_id = uuid4()  # TODO: Map to actual game_id from games table
            
            candidates.append({
                "game_id": game_id,
                "app_id": row["app_id"],
                "latest_signal_at": row["latest_signal_at"],
                "signal_count": row["signal_count"],
                "max_intent_score": row["max_intent_score"] or 0.0,
                "max_confidence": row["max_confidence"] or 0.0,
            })
        
        return candidates
    
    def compute_features(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute features for a candidate game.
        This is a simple implementation - can be extended.
        """
        return {
            "signal_count": candidate.get("signal_count", 0),
            "max_intent_score": candidate.get("max_intent_score", 0.0),
            "max_confidence": candidate.get("max_confidence", 0.0),
            "recency_days": (datetime.utcnow() - candidate.get("latest_signal_at", datetime.utcnow())).days if candidate.get("latest_signal_at") else 365,
        }
    
    def score_via_skills(
        self,
        candidate: Dict[str, Any],
        features: Dict[str, Any],
        skills: List[VoySkill]
    ) -> tuple[float, Dict[str, float], str]:
        """
        Score a candidate using skills.
        Returns: (total_score, skill_scores_dict, explanation)
        """
        skill_scores = {}
        total_score = 0.0
        
        for skill in skills:
            # Simple scoring: each skill contributes based on its weight and features
            if skill.name == "signal_count":
                score = features.get("signal_count", 0) * skill.weight * 0.1
            elif skill.name == "intent_score":
                score = features.get("max_intent_score", 0.0) * skill.weight * 0.01
            elif skill.name == "confidence":
                score = features.get("max_confidence", 0.0) * skill.weight * 0.01
            elif skill.name == "recency":
                recency_days = features.get("recency_days", 365)
                # More recent = better (inverse of days)
                score = max(0, (365 - recency_days) / 365) * skill.weight
            else:
                # Default: use intent_score
                score = features.get("max_intent_score", 0.0) * skill.weight * 0.01
            
            skill_scores[skill.name] = score
            total_score += score
        
        # Generate explanation
        top_skills = sorted(skill_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        explanation = f"Score: {total_score:.2f}. Top contributors: {', '.join([f'{name}({score:.2f})' for name, score in top_skills])}"
        
        return total_score, skill_scores, explanation
    
    def create_run(self, goal: str) -> VoyRun:
        """Create a new VOY run"""
        run = VoyRun(
            goal=goal,
            status="running",
            total_candidates=0,
            shortlist_size=0
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run
    
    def execute_run(self, run_id: UUID, shortlist_size: int = 10) -> VoyRun:
        """
        Execute a VOY run:
        1. Fetch candidates
        2. Compute features
        3. Score via skills
        4. Save shortlist
        """
        run = self.db.query(VoyRun).filter(VoyRun.id == run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found")
        
        goal = run.goal
        
        # Get skills for this goal
        skills = self.get_skills_for_goal(goal)
        if not skills:
            # Create default skills if none exist
            self._create_default_skills(goal)
            skills = self.get_skills_for_goal(goal)
        
        # Fetch candidates
        candidates = self.fetch_candidates(limit=100)
        run.total_candidates = len(candidates)
        
        # Score all candidates
        scored_items = []
        for candidate in candidates:
            features = self.compute_features(candidate)
            total_score, skill_scores, explanation = self.score_via_skills(candidate, features, skills)
            
            scored_items.append({
                "candidate": candidate,
                "features": features,
                "total_score": total_score,
                "skill_scores": skill_scores,
                "explanation": explanation
            })
        
        # Sort by score and take top N
        scored_items.sort(key=lambda x: x["total_score"], reverse=True)
        shortlist = scored_items[:shortlist_size]
        
        # Save shortlist items
        for rank, item in enumerate(shortlist, start=1):
            candidate = item["candidate"]
            app_id = candidate.get("app_id")
            
            # Get actual game title from database
            title = f"App {app_id}" if app_id else "Unknown"
            if app_id:
                try:
                    # Try to get title from steam_app_cache first, then from games table
                    # Use a simpler query to avoid transaction issues
                    title_query = text("""
                        SELECT COALESCE(
                            NULLIF((SELECT name FROM steam_app_cache WHERE steam_app_id = :app_id LIMIT 1), ''),
                            (SELECT title FROM games WHERE source = 'steam' AND source_id = :app_id_str LIMIT 1),
                            :fallback
                        ) as title
                    """)
                    result = self.db.execute(
                        title_query, 
                        {"app_id": app_id, "app_id_str": str(app_id), "fallback": f"App {app_id}"}
                    ).mappings().first()
                    if result and result.get("title"):
                        title = result["title"]
                except Exception as e:
                    logger.warning(f"Failed to get title for app_id {app_id}: {e}")
                    # Rollback any failed transaction
                    try:
                        self.db.rollback()
                    except:
                        pass
                    title = f"App {app_id}"
            
            run_item = VoyRunItem(
                run_id=run_id,
                game_id=candidate["game_id"],
                app_id=app_id,
                title=title,
                total_score=item["total_score"],
                explanation=item["explanation"],
                features_json=item["features"],
                skill_scores_json=item["skill_scores"],
                rank=rank
            )
            self.db.add(run_item)
        
        run.shortlist_size = len(shortlist)
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(run)
        
        return run
    
    def _create_default_skills(self, goal: Optional[str] = None):
        """Create default skills if none exist"""
        default_skills = [
            {"name": "signal_count", "description": "Number of signals", "weight": 1.0},
            {"name": "intent_score", "description": "Publisher intent score", "weight": 1.5},
            {"name": "confidence", "description": "Signal confidence", "weight": 1.2},
            {"name": "recency", "description": "Signal recency", "weight": 1.0},
        ]
        
        for skill_data in default_skills:
            existing = self.db.query(VoySkill).filter(
                VoySkill.name == skill_data["name"],
                VoySkill.goal == goal
            ).first()
            
            if not existing:
                skill = VoySkill(
                    name=skill_data["name"],
                    description=skill_data["description"],
                    weight=skill_data["weight"],
                    goal=goal
                )
                self.db.add(skill)
        
        self.db.commit()
    
    def _log_weight_change(
        self,
        run_item_id: UUID,
        skill_key: str,
        old_weight: float,
        new_weight: float,
        reason: Optional[str],
        source: str
    ):
        """Log weight change to voy_learning_log"""
        log_entry = VoyLearningLog(
            run_item_id=run_item_id,
            skill_key=skill_key,
            old_weight=old_weight,
            new_weight=new_weight,
            delta=new_weight - old_weight,
            reason=reason,
            source=source
        )
        self.db.add(log_entry)
    
    def _get_feedback_count_for_skill(self, skill_name: str) -> int:
        """Get feedback count for a skill (across all runs)"""
        # Count feedbacks for items that used this skill
        count = self.db.execute(
            text("""
                SELECT COUNT(DISTINCT vf.id)
                FROM voy_feedback vf
                JOIN voy_run_item vri ON vri.id = vf.run_item_id
                WHERE vri.skill_scores_json ? :skill_name
            """),
            {"skill_name": skill_name}
        ).scalar()
        return count or 0
    
    def process_feedback(self, run_item_id: UUID, feedback_type: str, notes: Optional[str] = None) -> VoyFeedback:
        """
        Process human feedback and update skill weights.
        Now respects learning config and logs all changes.
        """
        run_item = self.db.query(VoyRunItem).filter(VoyRunItem.id == run_item_id).first()
        if not run_item:
            raise ValueError(f"Run item {run_item_id} not found")
        
        # Create feedback record
        feedback = VoyFeedback(
            run_item_id=run_item_id,
            feedback_type=feedback_type,
            notes=notes
        )
        self.db.add(feedback)
        
        # Get learning config
        config = self.get_learning_config()
        
        # Check if learning is enabled
        if not config.learning_enabled:
            logger.info("Learning is disabled, skipping weight updates")
            self.db.commit()
            self.db.refresh(feedback)
            return feedback
        
        # Get frozen skills list
        frozen_skills = config.frozen_skills or []
        if isinstance(frozen_skills, str):
            try:
                frozen_skills = json.loads(frozen_skills)
            except:
                frozen_skills = []
        
        # Update skill weights based on feedback (if skill_scores available)
        if run_item.skill_scores_json:
            run = self.db.query(VoyRun).filter(VoyRun.id == run_item.run_id).first()
            goal = run.goal if run else None
            
            skills = self.get_skills_for_goal(goal)
            skill_dict = {s.name: s for s in skills}
            
            # Apply feedback-based learning
            changes_from_feedback = []
            
            for skill_name, score in run_item.skill_scores_json.items():
                # Skip frozen skills
                if skill_name in frozen_skills:
                    logger.info(f"Skill {skill_name} is frozen, skipping")
                    continue
                
                # Check min feedback count
                feedback_count = self._get_feedback_count_for_skill(skill_name)
                if feedback_count < config.min_feedback_count:
                    logger.info(f"Skill {skill_name} has {feedback_count} feedbacks, need {config.min_feedback_count}, skipping")
                    continue
                
                skill = skill_dict.get(skill_name)
                if not skill or score <= 0:
                    continue
                
                old_weight = skill.weight
                
                # Apply learning
                if feedback_type == "good":
                    delta = config.learning_rate * score
                    new_weight = min(config.max_skill_weight, old_weight + delta)
                elif feedback_type == "bad":
                    delta = -config.learning_rate * score
                    new_weight = max(config.min_skill_weight, old_weight + delta)
                else:
                    continue
                
                # Ensure delta doesn't exceed max_weight_delta
                actual_delta = new_weight - old_weight
                if abs(actual_delta) > config.max_weight_delta:
                    new_weight = old_weight + (config.max_weight_delta if actual_delta > 0 else -config.max_weight_delta)
                
                # Clamp to limits
                new_weight = max(config.min_skill_weight, min(config.max_skill_weight, new_weight))
                
                if abs(new_weight - old_weight) > 0.001:  # Only log if actually changed
                    skill.weight = new_weight
                    reason = f"Feedback: {feedback_type} (score={score:.2f})"
                    self._log_weight_change(run_item_id, skill_name, old_weight, new_weight, reason, "feedback")
                    changes_from_feedback.append({
                        "skill": skill_name,
                        "old_weight": old_weight,
                        "new_weight": new_weight
                    })
            
            # Apply GPT advice if enabled
            if config.allow_gpt_advice and changes_from_feedback:
                try:
                    # Prepare active skills for GPT
                    active_skills = [
                        {"key": s.name, "weight": s.weight}
                        for s in skills
                        if s.name not in frozen_skills
                    ]
                    
                    # Build prompt
                    prompt = self._gpt_service.build_prompt(
                        feedback_type=feedback_type,
                        feedback_reason=notes,
                        active_skills=active_skills,
                        frozen_skills=frozen_skills,
                        max_weight_delta=config.max_weight_delta,
                        min_skill_weight=config.min_skill_weight,
                        max_skill_weight=config.max_skill_weight
                    )
                    
                    # Call GPT
                    gpt_response = self._gpt_service.call_gpt(prompt)
                    
                    if gpt_response:
                        # Validate response
                        valid_skill_keys = [s.name for s in skills]
                        is_valid, suggestions = self._gpt_service.validate_gpt_response(
                            gpt_response,
                            valid_skill_keys,
                            frozen_skills,
                            config.max_weight_delta,
                            config.min_skill_weight,
                            config.max_skill_weight
                        )
                        
                        if is_valid:
                            # Apply GPT suggestions
                            for suggestion in suggestions:
                                skill_name = suggestion["skill"]
                                delta = suggestion["delta"]
                                reason = suggestion.get("reason", "GPT advice")
                                
                                skill = skill_dict.get(skill_name)
                                if not skill:
                                    continue
                                
                                old_weight = skill.weight
                                new_weight = max(
                                    config.min_skill_weight,
                                    min(config.max_skill_weight, old_weight + delta)
                                )
                                
                                if abs(new_weight - old_weight) > 0.001:
                                    skill.weight = new_weight
                                    self._log_weight_change(
                                        run_item_id, skill_name, old_weight, new_weight, reason, "gpt_advice"
                                    )
                                    logger.info(f"Applied GPT advice for {skill_name}: {old_weight} -> {new_weight}")
                except Exception as e:
                    logger.error(f"Error applying GPT advice: {e}", exc_info=True)
        
        self.db.commit()
        self.db.refresh(feedback)
        
        return feedback
