from sqlalchemy.orm import Session
from apps.db.models import Pitch, PitchStatus
from apps.api.schemas.pitches import PitchCreate
import logging

logger = logging.getLogger(__name__)


def create_pitch_and_score(db: Session, pitch_data: PitchCreate) -> Pitch:
    """
    Create a pitch and enqueue scoring task
    """
    # Normalize tags
    normalized_tags = [tag.lower().strip() for tag in pitch_data.tags]
    
    # Create pitch
    pitch = Pitch(
        dev_name=pitch_data.dev_name,
        email=pitch_data.email,
        studio_name=pitch_data.studio_name,
        team_size=pitch_data.team_size,
        released_before=pitch_data.released_before,
        timeline_months=pitch_data.timeline_months,
        pitch_text=pitch_data.pitch_text,
        hook_one_liner=pitch_data.hook_one_liner,
        links=pitch_data.links,
        build_link=pitch_data.build_link,
        video_link=pitch_data.video_link,
        tags=normalized_tags,
        status=PitchStatus.NEW
    )
    
    db.add(pitch)
    db.commit()
    db.refresh(pitch)
    
    # Enqueue scoring task asynchronously
    try:
        from apps.worker.tasks.score_pitch import score_pitch_task
        score_pitch_task.delay(str(pitch.id))
        logger.info(f"Enqueued scoring task for pitch {pitch.id}")
    except Exception as e:
        logger.error(f"Failed to enqueue scoring task: {e}")
    
    return pitch