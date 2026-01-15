from apps.worker.celery_app import celery_app
from apps.db.session import get_db_session
from apps.db.models import Pitch, PitchScore, PitchStatus
from apps.worker.scoring.comparables import find_comparables
from apps.worker.scoring.scoring_rules import compute_total_score
from apps.worker.scoring.verdict import assign_verdict
from apps.worker.scoring.explain import generate_explanations

# NEW: Import investor scoring
from apps.worker.scoring.investor_scoring import score_pitch_investor

from sqlalchemy import select
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="apps.worker.tasks.score_pitch.score_pitch_task")
def score_pitch_task(pitch_id: str, use_investor_scoring: bool = True):
    """
    Score a pitch asynchronously
    
    Args:
        pitch_id: UUID of the pitch
        use_investor_scoring: If True, use new investor scoring (default); if False, use legacy
    """
    logger.info(f"Starting scoring for pitch {pitch_id} (investor_mode={use_investor_scoring})")
    
    db = get_db_session()
    
    try:
        # Load pitch
        pitch_uuid = UUID(pitch_id)
        stmt = select(Pitch).where(Pitch.id == pitch_uuid)
        pitch = db.execute(stmt).scalar_one_or_none()
        
        if not pitch:
            logger.error(f"Pitch {pitch_id} not found")
            return {"status": "error", "error": "pitch_not_found"}
        
        if use_investor_scoring:
            # === NEW: INVESTOR SCORING PATH ===
            logger.info(f"Using investor scoring for pitch {pitch_id}")
            
            # Prepare pitch dict
            pitch_dict = {
                "hook_one_liner": pitch.hook_one_liner,
                "pitch_text": pitch.pitch_text,
                "tags": pitch.tags or [],
                "video_link": pitch.video_link,
                "build_link": pitch.build_link,
                "released_before": pitch.released_before,
                "team_size": pitch.team_size,
                "timeline_months": pitch.timeline_months,
            }
            
            # Run investor scoring
            result = score_pitch_investor(pitch_dict)
            
            # Create explanation structure
            explanation = {
                "decision_summary": result.decision_summary,
                "rationale_bullets": (
                    result.product_reasons[:2] +
                    result.gtm_reasons[:2] +
                    result.team_reasons[:1]
                ),
                "fixable_weaknesses": result.fixable_weaknesses,
                "next_actions": [{"title": a, "priority": 1} for a in result.investor_actions],
                "flags": result.flags,
            }
            
            # Create breakdown structure
            breakdown = {
                "version": "investor-1.0",
                "product_potential": result.product_potential,
                "product_confidence": result.product_confidence,
                "gtm_execution": result.gtm_execution,
                "gtm_confidence": result.gtm_confidence,
                "team_delivery": result.team_delivery,
                "team_confidence": result.team_confidence,
                "potential_gap": result.potential_gap,
                "fixability_score": result.fixability_score,
                "investment_profile": result.investment_profile,
            }
            
            # Create score record
            pitch_score = PitchScore(
                pitch_id=pitch.id,
                
                # Legacy fields (для обратной совместимости)
                score=result.legacy_score,
                verdict=result.legacy_verdict,
                explanation=explanation,
                breakdown=breakdown,
                
                # NEW: Investor fields
                product_potential=result.product_potential,
                product_confidence=result.product_confidence,
                gtm_execution=result.gtm_execution,
                gtm_confidence=result.gtm_confidence,
                team_delivery=result.team_delivery,
                team_confidence=result.team_confidence,
                potential_gap=result.potential_gap,
                fixability_score=result.fixability_score,
                investment_profile=result.investment_profile,
            )
            
            db.add(pitch_score)
            
            # Update pitch
            pitch.score = result.legacy_score
            pitch.status = PitchStatus.SCORED
            
            db.commit()
            
            logger.info(
                f"Scored pitch {pitch_id}: {result.legacy_score:.1f}/100 - "
                f"{result.legacy_verdict} - Profile: {result.investment_profile} - "
                f"Gap: {result.potential_gap:.1f} - Fix: {result.fixability_score:.1f}"
            )
            
            return {
                "status": "success",
                "pitch_id": pitch_id,
                "score": result.legacy_score,
                "verdict": result.legacy_verdict,
                "investment_profile": result.investment_profile,
                "potential_gap": result.potential_gap,
                "fixability_score": result.fixability_score,
            }
        
        else:
            # === LEGACY SCORING PATH ===
            logger.info(f"Using legacy scoring for pitch {pitch_id}")
            
            # Check if already scored
            if pitch.score:
                logger.info(f"Pitch {pitch_id} already scored")
                return {"status": "already_scored"}
            
            # Find comparables
            comparables = find_comparables(
                db,
                pitch.tags,
                pitch.pitch_text,
                pitch.hook_one_liner
            )
            
            # Compute scores
            score_breakdown = compute_total_score(db, pitch, comparables)
            
            # Assign verdict
            verdict = assign_verdict(score_breakdown["score_total"])
            
            # Generate explanations
            why_yes, why_no, next_step = generate_explanations(
                pitch,
                score_breakdown,
                comparables,
                verdict
            )
            
            # Create explanation for new structure
            explanation = {
                "why_yes": why_yes,
                "why_no": why_no,
                "next_step": next_step,
            }
            
            breakdown = {
                "version": "legacy-1.0",
                "score_hook": score_breakdown["score_hook"],
                "score_market": score_breakdown["score_market"],
                "score_team": score_breakdown["score_team"],
                "score_steam": score_breakdown["score_steam"],
                "score_asymmetry": score_breakdown["score_asymmetry"],
                "reasons": score_breakdown["reasons"],
            }
            
            # Create score record
            pitch_score = PitchScore(
                pitch_id=pitch.id,
                score=float(score_breakdown["score_total"]),
                verdict=verdict.value,
                explanation=explanation,
                breakdown=breakdown,
            )
            
            db.add(pitch_score)
            
            # Update pitch status
            pitch.status = PitchStatus.SCORED
            pitch.score = float(score_breakdown["score_total"])
            
            db.commit()
            
            logger.info(f"Scored pitch {pitch_id}: {score_breakdown['score_total']}/100 - {verdict.value}")
            
            return {
                "status": "success",
                "pitch_id": pitch_id,
                "score": score_breakdown["score_total"],
                "verdict": verdict.value
            }
        
    except Exception as e:
        logger.error(f"Failed to score pitch {pitch_id}: {e}", exc_info=True)
        db.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        db.close()