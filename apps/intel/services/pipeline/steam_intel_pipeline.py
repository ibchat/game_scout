"""
Steam Intel Pipeline Orchestrator
Full pipeline: collect → extract → event → brief → publish
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from apps.intel.db.models import (
    IntelSource, IntelRawItem, IntelExtractedItem, IntelEvent, IntelCluster
)
from apps.intel.services.collectors import RSSCollector, SteamNewsCollector
from apps.intel.services.business_brief_generator import generate_business_brief, classify_signal_type
from apps.intel.services.publishers.telegram_publisher import TelegramPublisher
from apps.intel.policy.policy_engine import load_policy, validate_source_url

logger = logging.getLogger(__name__)


def extract_from_raw_item(raw_item: IntelRawItem, db: Session) -> Optional[IntelExtractedItem]:
    """
    Simple extractor: creates IntelExtractedItem from IntelRawItem.
    Uses model fields: lang, title_norm, url_norm, text, meta.
    """
    try:
        # Check if already extracted
        existing = db.query(IntelExtractedItem).filter(
            IntelExtractedItem.raw_item_id == raw_item.id
        ).first()
        
        if existing:
            return existing
        
        # Detect language
        from apps.intel.services.business_brief_generator import detect_language
        text = raw_item.snippet or raw_item.title or ""
        lang = detect_language(text)
        
        # Create extracted item
        extracted = IntelExtractedItem(
            raw_item_id=raw_item.id,
            lang=lang,
            title_norm=raw_item.title or "",
            url_norm=raw_item.url,
            text=text,
            meta={"snippet": raw_item.snippet, "raw_payload": raw_item.raw_payload}
        )
        
        db.add(extracted)
        db.commit()
        db.refresh(extracted)
        
        return extracted
        
    except Exception as e:
        logger.error(f"Failed to extract from raw item {raw_item.id}: {e}", exc_info=True)
        db.rollback()
        return None


def create_or_update_event(
    extracted_item: IntelExtractedItem,
    db: Session
) -> Optional[IntelEvent]:
    """
    Create or update IntelEvent from extracted item.
    Creates a simple cluster for each extracted item (can be improved later).
    """
    try:
        # Create or get cluster for this extracted item
        cluster = db.query(IntelCluster).filter(
            IntelCluster.representative_extracted_id == extracted_item.id
        ).first()
        
        if not cluster:
            cluster = IntelCluster(
                representative_extracted_id=extracted_item.id,
                member_extracted_ids=[str(extracted_item.id)]
            )
            db.add(cluster)
            db.commit()
            db.refresh(cluster)
        
        # Check if event already exists
        existing = db.query(IntelEvent).filter(
            IntelEvent.cluster_id == cluster.id
        ).first()
        
        if existing:
            return existing
        
        # Classify signal type
        text = extracted_item.text or extracted_item.title_norm or ""
        signal_type = classify_signal_type(text)
        
        # Translate title if needed
        from apps.intel.services.business_brief_generator import translate_to_russian, detect_language
        title_ru = extracted_item.title_norm
        if detect_language(title_ru) != "ru":
            title_ru = translate_to_russian(title_ru)
        
        what_happened_ru = extracted_item.text or "нет данных"
        if detect_language(what_happened_ru) != "ru":
            what_happened_ru = translate_to_russian(what_happened_ru)
        
        # Create event
        event = IntelEvent(
            cluster_id=cluster.id,
            event_type=signal_type,
            score=0,  # Can be calculated later
            status="ready",
            title_ru=title_ru,
            what_happened_ru=what_happened_ru,
            why_it_matters_ru=None,  # Will be filled by brief generator
            sources=[extracted_item.url_norm] if extracted_item.url_norm else [],
            autopublish_eligible=True
        )
        
        db.add(event)
        db.commit()
        db.refresh(event)
        
        return event
        
    except Exception as e:
        logger.error(f"Failed to create event from extracted item {extracted_item.id}: {e}", exc_info=True)
        db.rollback()
        return None


def run_pipeline(
    sources: List[str],
    db: Session,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Run full Steam Intel pipeline.
    
    Flow:
    1. Collect raw items from sources
    2. Extract structured data
    3. Create/update events
    4. Generate business briefs
    5. Validate policy
    6. Publish to Telegram
    
    Args:
        sources: List of source names to collect from
        db: Database session
        dry_run: If True, don't actually publish
    
    Returns:
        Summary dict with counts
    """
    logger.info(f"Starting Steam Intel pipeline: sources={sources}, dry_run={dry_run}")
    
    policy = load_policy()
    allowed_types = policy.get("allowed_event_types_for_autopublish", [])
    
    # Initialize collectors
    rss_collector = RSSCollector(db)
    steam_collector = SteamNewsCollector(db)
    
    # Step 1: Collect
    collected_count = 0
    for source_name in sources:
        source = db.query(IntelSource).filter(
            IntelSource.name == source_name,
            IntelSource.is_enabled == True
        ).first()
        
        if not source:
            logger.warning(f"Source not found or disabled: {source_name}")
            continue
        
        # Validate source URL
        decision, reason = validate_source_url(source.url)
        if decision != "allow":
            logger.warning(f"Source URL rejected: {source.url} - {reason}")
            continue
        
        # Collect based on type
        try:
            if source.type == "rss":
                result = rss_collector.collect_source(source)
                collected_count += result
            elif source.type == "steam":
                result = steam_collector.collect_source(source)
                collected_count += result
            else:
                logger.warning(f"Unknown source type: {source.type}")
        except Exception as e:
            logger.error(f"Collection failed for {source_name}: {e}", exc_info=True)
    
    # Step 2: Extract
    raw_items = db.query(IntelRawItem).filter(
        IntelRawItem.fetched_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).limit(100).all()
    
    extracted_count = 0
    for raw_item in raw_items:
        extracted = extract_from_raw_item(raw_item, db)
        if extracted:
            extracted_count += 1
    
    # Step 3: Create events
    # Get recently extracted items (created today)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    extracted_items = db.query(IntelExtractedItem).join(
        IntelRawItem, IntelExtractedItem.raw_item_id == IntelRawItem.id
    ).filter(
        IntelRawItem.fetched_at >= today_start
    ).limit(50).all()
    
    events_created = 0
    events = []
    for extracted_item in extracted_items:
        event = create_or_update_event(extracted_item, db)
        if event:
            events.append(event)
            events_created += 1
    
    # Step 4: Generate briefs and publish
    publisher = TelegramPublisher(db)
    published_count = 0
    skipped_count = 0
    briefs_generated = 0
    
    for event in events:
        try:
            # Check if event type is allowed
            if event.event_type not in allowed_types:
                logger.debug(f"Event type {event.event_type} not in allowed_types, skipping")
                skipped_count += 1
                continue
            
            # Generate brief if not exists
            if not event.business_brief_json:
                brief = generate_business_brief(event, db)
                event.business_brief_json = brief
                event.business_brief_generated_at = datetime.utcnow()
                briefs_generated += 1
                db.commit()
            else:
                brief = event.business_brief_json
            
            # Publish
            result = publisher.publish_event(event, brief, dry_run=dry_run)
            
            if result.status == "published":
                published_count += 1
            elif result.status == "skipped":
                skipped_count += 1
            else:
                logger.warning(f"Publish failed for event {event.id}: {result.error}")
                skipped_count += 1
                
        except Exception as e:
            logger.error(f"Failed to process event {event.id}: {e}", exc_info=True)
            skipped_count += 1
            db.rollback()
    
    return {
        "collected": collected_count,
        "extracted": extracted_count,
        "events_created": events_created,
        "briefs_generated": briefs_generated,
        "published": published_count,
        "skipped": skipped_count,
        "dry_run": dry_run
    }
