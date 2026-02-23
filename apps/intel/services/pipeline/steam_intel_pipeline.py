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
from apps.intel.services.significance import score_event
from apps.intel.services.steam_mention_detector import detect_steam_relevance, extract_steam_appid
from apps.intel.services.translator import translate_to_ru, message_is_russian, detect_language
from apps.intel.policy.policy_engine import load_policy, validate_source_url

logger = logging.getLogger(__name__)


def extract_from_raw_item(raw_item: IntelRawItem, db: Session) -> Optional[IntelExtractedItem]:
    """
    Wide extractor: creates IntelExtractedItem from IntelRawItem for almost all items.
    Creates extracted item if title OR url exists (wide approach).
    Steam relevance filtering happens later in the pipeline.
    
    Goal: increase Raw -> Extracted conversion from 0.18% to 20-40%.
    """
    try:
        # Check if already extracted
        existing = db.query(IntelExtractedItem).filter(
            IntelExtractedItem.raw_item_id == raw_item.id
        ).first()
        
        if existing:
            return existing
        
        # WIDE EXTRACTION: create extracted if title OR url OR snippet exists
        # Goal: ≥10% conversion (was 0.8%)
        if not raw_item.title and not raw_item.url and not raw_item.snippet:
            logger.debug(f"Raw item {raw_item.id} skipped: no title, url, or snippet")
            return None
        
        # Get text for analysis
        text = raw_item.snippet or raw_item.title or ""
        url_text = raw_item.url or ""
        combined_text = f"{text} {url_text}"
        
        # Detect language
        from apps.intel.services.business_brief_generator import detect_language as detect_lang
        lang = detect_lang(text) if text else "unknown"
        
        # Extract Steam appid if present
        appid = extract_steam_appid(combined_text)
        
        # Check Steam relevance (but don't skip - just mark in meta)
        policy = load_policy()
        steam_relevance_required = policy.get("steam_relevance_required", True)
        
        relevance_reason = None
        relevance_score = 0
        matched_keywords = []
        is_relevant = False
        
        if steam_relevance_required:
            min_relevance = policy.get("relevance", {}).get("min_relevance_score", 20)
            is_relevant, relevance_reason, relevance_score, matched_keywords = detect_steam_relevance(combined_text, min_relevance)
            # Don't skip here - create extracted item anyway, relevance will filter later
        
        # Create extracted item (always if title or url exists)
        meta = {
            "snippet": raw_item.snippet,
            "raw_payload": raw_item.raw_payload,
            "steam_appid": appid,
            "relevance_reason": relevance_reason if steam_relevance_required else None,
            "relevance_score": relevance_score if steam_relevance_required else None,
            "matched_keywords": matched_keywords if steam_relevance_required else [],
            "is_steam_relevant": is_relevant if steam_relevance_required else None,
            "extraction_wide_mode": True  # Mark as wide extraction
        }
        
        extracted = IntelExtractedItem(
            raw_item_id=raw_item.id,
            lang=lang,
            title_norm=raw_item.title or "Untitled",
            url_norm=raw_item.url or "",
            text=text or "нет данных",
            meta=meta
        )
        
        db.add(extracted)
        db.commit()
        db.refresh(extracted)
        
        if not is_relevant and steam_relevance_required:
            logger.debug(f"Extracted item {extracted.id} created but not Steam-relevant (score={relevance_score})")
        
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
        
        # Translate title if needed (strict Russian output)
        title_ru = extracted_item.title_norm
        source_lang = extracted_item.lang or detect_language(title_ru)
        translation_applied = False
        
        if source_lang != "ru":
            try:
                logger.info(f"Translating title from {source_lang} to ru")
                title_ru = translate_to_ru(title_ru, source_lang)
                translation_applied = True
            except Exception as e:
                logger.warning(f"Translation failed for title: {e}. Using original text.")
                # If translation fails but text might be Russian, try to use as-is
                # Otherwise, skip this event to avoid publishing non-Russian content
                if "not configured" in str(e).lower() or "not available" in str(e).lower():
                    logger.warning(f"Skipping event due to missing translation service")
                    raise  # Skip event if translation service not available
                # For other errors, also skip to be safe
                raise
        
        what_happened_ru = extracted_item.text or "нет данных"
        if source_lang != "ru":
            try:
                what_happened_ru = translate_to_ru(what_happened_ru, source_lang)
                translation_applied = True
            except Exception as e:
                logger.warning(f"Translation failed for what_happened: {e}. Using original text.")
                # Same logic: skip if translation service not available
                if "not configured" in str(e).lower() or "not available" in str(e).lower():
                    logger.warning(f"Skipping event due to missing translation service")
                    raise
                raise
        
        # Get relevance score from extracted item meta
        relevance_score = extracted_item.meta.get("relevance_score") if extracted_item.meta else None
        relevance_reason = extracted_item.meta.get("relevance_reason") if extracted_item.meta else None
        
        # Create event (all content must be in Russian)
        event = IntelEvent(
            cluster_id=cluster.id,
            event_type=signal_type,
            score=0,  # Legacy field, use significance_score instead
            status="ready",
            title_ru=title_ru,
            what_happened_ru=what_happened_ru,
            why_it_matters_ru=None,  # Will be filled by brief generator
            sources=[extracted_item.url_norm] if extracted_item.url_norm else [],
            autopublish_eligible=False,  # Will be calculated after scoring
            llm_meta={
                "translation_applied": translation_applied,
                "source_language": source_lang,
                "final_language": "ru",
                "steam_relevance_score": relevance_score,
                "steam_relevance_reason": relevance_reason
            }
        )
        
        db.add(event)
        db.commit()
        db.refresh(event)
        
        # Calculate significance score
        policy = load_policy()
        allowed_types = policy.get("allowed_event_types_for_autopublish", [])
        score, reason, category, confidence = score_event(event, extracted_item, policy)
        
        # Update event with significance
        event.significance_score = score
        event.significance_reason = reason
        event.event_type = category  # Update category if changed
        
        # Calculate eligibility based on significance thresholds
        sig_config = policy.get("significance", {})
        min_score = sig_config.get("min_score_to_autopublish", 35)  # Use policy value, default 35
        min_confidence = sig_config.get("min_confidence_to_autopublish", 0.7)  # Use policy value, default 0.7
        always_publish = sig_config.get("always_publish_categories", [])
        never_autopublish = sig_config.get("never_autopublish_categories", [])
        
        # Eligibility logic
        eligible = (
            (score >= min_score or category in always_publish) and
            confidence >= min_confidence and
            category not in never_autopublish and
            category in allowed_types
        )
        
        event.autopublish_eligible = eligible
        
        db.commit()
        db.refresh(event)
        
        return event
        
    except Exception as e:
        # Save extracted_item.id before rollback (may not be accessible after)
        extracted_id = str(extracted_item.id) if extracted_item and hasattr(extracted_item, 'id') else "unknown"
        logger.error(f"Failed to create event from extracted item {extracted_id}: {e}", exc_info=True)
        db.rollback()
        return None


def run_pipeline(
    sources: Optional[List[str]] = None,
    db: Session = None,
    dry_run: bool = False,
    max_posts_per_run: Optional[int] = None
) -> Dict[str, Any]:
    """
    Run full Steam Intel pipeline.
    
    Flow:
    1. Collect raw items from sources (ALL active if sources=None)
    2. Extract structured data with Steam relevance filter
    3. Create/update events
    4. Generate business briefs
    5. Translate to Russian (if needed)
    6. Calculate significance scores
    7. Filter by eligibility
    8. Publish to Telegram
    
    Args:
        sources: List of source names to collect from. If None, uses ALL active sources.
        db: Database session
        dry_run: If True, don't actually publish
    
    Returns:
        Summary dict with counts including per-source stats
    """
    if db is None:
        from apps.db.session import SessionLocal
        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    
    try:
        policy = load_policy()
        allowed_types = policy.get("allowed_event_types_for_autopublish", [])
        
        # ARCHITECTURE FIX: Collect stage ALWAYS executes
        # If sources not specified, get ALL active sources (rss, reddit_rss, steam)
        collect_reason = "explicit_sources"
        if sources is None or (isinstance(sources, list) and len(sources) == 0):
            active_sources = db.query(IntelSource).filter(
                IntelSource.is_enabled == True
            ).filter(
                IntelSource.type.in_(["rss", "reddit_rss", "steam"])
            ).all()
            sources = [s.name for s in active_sources]
            collect_reason = "all_active_sources"
            logger.info(f"[INTEL][COLLECT] No sources specified, using {len(sources)} active sources (types: rss, reddit_rss, steam)")
        
        # Check if we have sources to collect from
        if not sources or len(sources) == 0:
            enabled_count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
            logger.warning(f"[INTEL][COLLECT] No sources available for collection (enabled sources in DB: {enabled_count})")
            collect_reason = "no_sources_available"
            # Return early with diagnostic info
            return {
                "collect_stage_executed": False,
                "collect_reason": collect_reason,
                "sources_used": 0,
                "collected": 0,
                "saved": 0,
                "raw_saved": 0,
                "raw_duplicates": 0,
                "sources_processed": 0,
                "sources_failed": 0,
                "error": "no_sources_available",
                "enabled_sources_in_db": enabled_count
            }
        
        logger.info(f"[INTEL][COLLECT] Starting Steam Intel pipeline: sources={len(sources)} sources, dry_run={dry_run}, reason={collect_reason}")
        
        # Check if forced collect mode is enabled
        import os
        force_collect = os.getenv("PIPELINE_FORCE_COLLECT", "false").lower() == "true"
        if force_collect:
            logger.info("[INTEL][COLLECT] FORCE_COLLECT mode enabled - will collect even if already collected")
        
        # Initialize collectors
        rss_collector = RSSCollector(db)
        steam_collector = SteamNewsCollector(db)
        
        # Step 1: Collect from all sources (ALWAYS EXECUTES if sources exist)
        collected_count = 0
        raw_saved = 0
        raw_duplicates = 0
        sources_processed = []
        sources_with_errors = []
        items_per_source = {}
        collect_stage_executed = True  # Set to True BEFORE loop - collect stage WILL execute
        
        logger.info(f"[INTEL][COLLECT] Collecting from {len(sources)} sources...")
        
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
                collect_stage_executed = True
                logger.info(f"[INTEL][COLLECT] Collecting from source: {source_name} (type: {source.type})")
                
                if source.type == "rss":
                    collect_result = rss_collector.collect(source)
                    collected_from_source = collect_result.get("collected", 0)
                    saved_from_source = collect_result.get("saved", 0)
                    duplicates_from_source = collect_result.get("duplicates", 0)
                    collected_count += collected_from_source
                    raw_saved += saved_from_source
                    raw_duplicates += duplicates_from_source
                    items_per_source[source_name] = saved_from_source
                    logger.info(f"[INTEL][COLLECT] Source {source_name}: collected={collected_from_source}, saved={saved_from_source}, duplicates={duplicates_from_source}")
                elif source.type == "steam":
                    collect_result = steam_collector.collect(source)
                    collected_from_source = collect_result.get("collected", 0)
                    saved_from_source = collect_result.get("saved", 0)
                    duplicates_from_source = collect_result.get("duplicates", 0)
                    collected_count += collected_from_source
                    raw_saved += saved_from_source
                    raw_duplicates += duplicates_from_source
                    items_per_source[source_name] = saved_from_source
                    logger.info(f"[INTEL][COLLECT] Source {source_name}: collected={collected_from_source}, saved={saved_from_source}, duplicates={duplicates_from_source}")
                elif source.type == "reddit_rss":
                    from apps.intel.services.collectors.reddit_rss_collector import RedditRSSCollector
                    reddit_collector = RedditRSSCollector(db)
                    collect_result = reddit_collector.collect(source)
                    collected_from_source = collect_result.get("collected", 0)
                    saved_from_source = collect_result.get("saved", 0)
                    duplicates_from_source = collect_result.get("duplicates", 0)
                    collected_count += collected_from_source
                    raw_saved += saved_from_source
                    raw_duplicates += duplicates_from_source
                    items_per_source[source_name] = saved_from_source
                    logger.info(f"[INTEL][COLLECT] Source {source_name}: collected={collected_from_source}, saved={saved_from_source}, duplicates={duplicates_from_source}")
                else:
                    logger.warning(f"[INTEL][COLLECT] Unknown source type: {source.type}")
                    items_per_source[source_name] = 0
                
                sources_processed.append(source_name)
            except httpx.HTTPStatusError as e:
                # Track HTTP errors for source health
                error_code = e.response.status_code if hasattr(e, 'response') else None
                from apps.intel.services.source_health import track_source_error
                track_source_error(db, source, error_code=error_code, error_message=str(e))
                
                logger.error(f"HTTP error collecting from source {source_name}: {e}", exc_info=True)
                sources_with_errors.append({
                    "source": source_name,
                    "error": f"HTTP {error_code}: {str(e)[:200]}",
                    "error_code": error_code
                })
                items_per_source[source_name] = 0
            except Exception as e:
                logger.error(f"Error collecting from source {source_name}: {e}", exc_info=True)
                sources_with_errors.append({
                    "source": source_name,
                    "error": str(e)[:200],
                    "error_code": None
                })
                items_per_source[source_name] = 0
        
        # ARCHITECTURE FIX: Protection against silent-skip
        # If we have enabled sources but collected 0, log WARNING
        enabled_sources_count = db.query(IntelSource).filter(IntelSource.is_enabled == True).count()
        if enabled_sources_count > 0 and collected_count == 0 and raw_saved == 0:
            logger.warning(f"[INTEL][COLLECT] ⚠️  CRITICAL: 0 items collected despite {enabled_sources_count} enabled sources!")
            logger.warning(f"[INTEL][COLLECT] Sources processed: {len(sources_processed)}, Sources failed: {len(sources_with_errors)}")
            if sources_with_errors:
                logger.warning(f"[INTEL][COLLECT] Error breakdown: {sources_with_errors[:5]}")  # Show first 5 errors
        
        logger.info(f"[INTEL][COLLECT] Collect stage complete: collected={collected_count}, saved={raw_saved}, duplicates={raw_duplicates}, sources_processed={len(sources_processed)}, sources_failed={len(sources_with_errors)}")
        
        # Step 2: Extract (ETAP 3)
        logger.info(f"[INTEL][EXTRACT] Starting extraction from raw items (last 24h)")
        # Get raw items from last 24 hours (for daily run)
        from datetime import timedelta
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        raw_items = db.query(IntelRawItem).filter(
            IntelRawItem.fetched_at >= cutoff_time
        ).limit(policy.get("pipeline_batch_size", 100)).all()
        
        logger.info(f"[INTEL][EXTRACT] Found {len(raw_items)} raw items to process")
        
        extracted_count = 0
        relevant_count = 0
        translated_count = 0
        for raw_item in raw_items:
            extracted = extract_from_raw_item(raw_item, db)
            if extracted:
                extracted_count += 1
                # Check if relevant (has relevance_score in meta)
                if extracted.meta and extracted.meta.get("relevance_score", 0) >= 20:
                    relevant_count += 1
                # Check if translated (has translation_meta)
                if extracted.meta and extracted.meta.get("translation_applied"):
                    translated_count += 1
        
        logger.info(f"[INTEL][EXTRACT] Extraction complete: {extracted_count} extracted, {relevant_count} relevant")
        
        # Step 3: Create events
        # Get recently extracted items (extracted in last 24 hours)
        # Use extracted_at instead of fetched_at for proper daily run filtering
        # CRITICAL: Check if extracted_at column exists, log error if not
        try:
            extracted_items = db.query(IntelExtractedItem).filter(
                IntelExtractedItem.extracted_at >= cutoff_time
            ).limit(policy.get("pipeline_batch_size", 50)).all()
        except Exception as e:
            if "extracted_at" in str(e).lower() or "column" in str(e).lower():
                logger.error("CRITICAL: extracted_at column missing! Run migration 016: alembic upgrade head")
                raise RuntimeError("extracted_at column missing - migration 016 not applied") from e
            raise
        
        events_created = 0
        events = []
        for extracted_item in extracted_items:
            event = create_or_update_event(extracted_item, db)
            if event:
                events.append(event)
                events_created += 1
        
        # Step 4: Calculate significance for all events (if not already calculated)
        logger.info(f"[INTEL][SCORE] Calculating significance for {len(events)} events")
        sig_config = policy.get("significance", {})
        min_score = sig_config.get("min_score_to_autopublish", 35)  # Use policy value, default 35
        min_confidence = sig_config.get("min_confidence_to_autopublish", 0.7)  # Use policy value, default 0.7
        always_publish = sig_config.get("always_publish_categories", [])
        never_autopublish = sig_config.get("never_autopublish_categories", [])
        
        eligible_count = 0
        for event in events:
            # Recalculate significance if not set
            if event.significance_score == 0 or not event.significance_reason:
                # Get extracted item for this event
                extracted_item = None
                if event.cluster_id:
                    cluster = db.query(IntelCluster).filter(IntelCluster.id == event.cluster_id).first()
                    if cluster:
                        extracted_item = db.query(IntelExtractedItem).filter(
                            IntelExtractedItem.id == cluster.representative_extracted_id
                        ).first()
                
                score, reason, category, confidence = score_event(event, extracted_item, policy)
                
                # ETAP 4: Guarantee baseline score >= 25
                if score < 25:
                    logger.warning(f"[INTEL][SCORE] Event {event.id} has score {score} < 25, enforcing baseline=25")
                    score = 25
                
                event.significance_score = score
                event.significance_reason = reason
                event.event_type = category
                
                # Recalculate eligibility
                eligible = (
                    (score >= min_score or category in always_publish) and
                    confidence >= min_confidence and
                    category not in never_autopublish and
                    category in allowed_types
                )
                event.autopublish_eligible = eligible
                
                if eligible:
                    eligible_count += 1
                
                db.commit()
            elif event.autopublish_eligible:
                eligible_count += 1
        
        # Step 5: Generate briefs and publish
        publisher = TelegramPublisher(db)
        published_count = 0
        skipped_count = 0
        briefs_generated = 0
        skip_breakdown = {
            "not_relevant": 0,
            "low_score": 0,
            "translation_failed": 0,
            "russian_check_failed": 0,
            "already_published": 0,
            "rate_limited": 0,
            "event_type_not_allowed": 0,
            "brief_generation_failed": 0,
            "other": 0
        }
        
        # Get only eligible events for publishing
        eligible_events = [e for e in events if e.autopublish_eligible]
        logger.info(f"Processing {len(eligible_events)} eligible events out of {len(events)} total")
        
        # Apply max_posts_per_run limit if specified (for daily mode)
        if max_posts_per_run is not None and max_posts_per_run > 0:
            if len(eligible_events) > max_posts_per_run:
                logger.info(f"Limiting to {max_posts_per_run} posts per run (daily mode), skipping {len(eligible_events) - max_posts_per_run} events")
                # Sort by significance_score descending and take top N
                eligible_events = sorted(eligible_events, key=lambda e: e.significance_score or 0, reverse=True)[:max_posts_per_run]
        
        for event in eligible_events:
            try:
                # Check if event type is allowed
                if event.event_type not in allowed_types:
                    logger.debug(f"Event type {event.event_type} not in allowed_types, skipping")
                    from apps.intel.db.models import IntelPublishLog
                    skip_reason = f"event_type_not_allowed ({event.event_type})"
                    existing_log = db.query(IntelPublishLog).filter(
                        IntelPublishLog.event_id == event.id,
                        IntelPublishLog.status.in_(["skipped", "published"])
                    ).first()
                    if not existing_log:
                        publish_log = IntelPublishLog(
                            event_id=event.id,
                            channel_id="free",
                            telegram_message_id="",
                            status="skipped",
                            error=skip_reason,
                            payload={"event_type": event.event_type, "allowed_types": allowed_types}
                        )
                        db.add(publish_log)
                        db.commit()
                    skipped_count += 1
                    skip_breakdown["event_type_not_allowed"] += 1
                    continue
                
                # Generate brief (always regenerate for eligible events to ensure freshness)
                logger.info(f"Generating brief for event {event.id} (type={event.event_type}, score={event.significance_score})")
                brief = generate_business_brief(event, db)
                if brief and brief.get("title") and brief.get("what_happened"):
                    event.business_brief_json = brief
                    event.business_brief_generated_at = datetime.utcnow()
                    briefs_generated += 1
                    db.commit()
                    logger.info(f"Brief generated for event {event.id}: title='{brief.get('title', '')[:50]}...'")
                else:
                    logger.warning(f"Failed to generate brief for event {event.id} (brief={brief})")
                    from apps.intel.db.models import IntelPublishLog
                    skip_reason = "brief_generation_failed"
                    existing_log = db.query(IntelPublishLog).filter(
                        IntelPublishLog.event_id == event.id,
                        IntelPublishLog.status == "skipped"
                    ).first()
                    if not existing_log:
                        publish_log = IntelPublishLog(
                            event_id=event.id,
                            channel_id="free",
                            telegram_message_id="",
                            status="skipped",
                            error=skip_reason,
                            payload={"brief": brief}
                        )
                        db.add(publish_log)
                        db.commit()
                    skipped_count += 1
                    skip_breakdown["brief_generation_failed"] += 1
                    continue
                
                # Check max_posts_per_run limit (for daily mode)
                if max_posts_per_run is not None and published_count >= max_posts_per_run:
                    logger.info(f"Reached max_posts_per_run limit ({max_posts_per_run}), skipping remaining events")
                    skip_reason = "rate_limited_max_posts_per_run"
                    from apps.intel.db.models import IntelPublishLog
                    existing_log = db.query(IntelPublishLog).filter(
                        IntelPublishLog.event_id == event.id,
                        IntelPublishLog.status == "skipped"
                    ).first()
                    if not existing_log:
                        publish_log = IntelPublishLog(
                            event_id=event.id,
                            channel_id="free",
                            telegram_message_id="",
                            status="skipped",
                            error=skip_reason,
                            payload={"max_posts_per_run": max_posts_per_run, "published_count": published_count}
                        )
                        db.add(publish_log)
                        db.commit()
                    skipped_count += 1
                    skip_breakdown["rate_limited"] += 1
                    continue
                
                # Publish (publisher expects brief parameter)
                result = publisher.publish_event(event, brief, dry_run=dry_run)
                
                if result.status == "published":
                    published_count += 1
                    logger.info(f"[INTEL][PUBLISH] ✅ Event {event.id} published successfully (message_id={result.message_id})")
                elif result.status == "skipped":
                    skip_reason = result.error or "unknown_skip_reason"
                    logger.info(f"[INTEL][PUBLISH] ⏭️  Event {event.id} skipped: {skip_reason}")
                    skipped_count += 1
                    # Categorize skip reason
                    if "non_russian" in skip_reason.lower() or "russian" in skip_reason.lower():
                        skip_breakdown["russian_check_failed"] += 1
                    elif "translation" in skip_reason.lower() or "translation_unavailable" in skip_reason:
                        skip_breakdown["translation_failed"] += 1
                    elif "already published" in skip_reason.lower() or "already_published" in skip_reason:
                        skip_breakdown["already_published"] += 1
                    elif "rate limit" in skip_reason.lower() or "rate_limit" in skip_reason:
                        skip_breakdown["rate_limited"] += 1
                    elif "event_type_not_allowed" in skip_reason:
                        skip_breakdown["event_type_not_allowed"] += 1
                    else:
                        skip_breakdown["other"] += 1
                else:
                    logger.warning(f"❌ Publish failed for event {event.id}: {result.error}")
                    skipped_count += 1
                    skip_breakdown["other"] += 1
                    
            except Exception as e:
                logger.error(f"Failed to process event {event.id}: {e}", exc_info=True)
                from apps.intel.db.models import IntelPublishLog
                existing_log = db.query(IntelPublishLog).filter(
                    IntelPublishLog.event_id == event.id,
                    IntelPublishLog.status == "failed"
                ).first()
                if not existing_log:
                    publish_log = IntelPublishLog(
                        event_id=event.id,
                        channel_id="free",
                        telegram_message_id="",
                        status="failed",
                        error=f"Exception: {str(e)[:200]}"
                    )
                    db.add(publish_log)
                    db.commit()
                skipped_count += 1
                db.rollback()
        
        # Calculate stats with extraction ratio
        # Raw layer diagnostics (ETAP 2)
        from datetime import timedelta
        raw_last_24h = db.query(IntelRawItem).filter(
            IntelRawItem.fetched_at >= cutoff_time
        ).count()
        
        raw_last_6h = db.query(IntelRawItem).filter(
            IntelRawItem.fetched_at >= datetime.utcnow() - timedelta(hours=6)
        ).count()
        
        # Raw per source (last 24h)
        raw_per_source = {}
        for source_name in sources_processed:
            source = db.query(IntelSource).filter(IntelSource.name == source_name).first()
            if source:
                count = db.query(IntelRawItem).filter(
                    IntelRawItem.source_id == source.id,
                    IntelRawItem.fetched_at >= cutoff_time
                ).count()
                raw_per_source[source_name] = count
        
        total_raw_24h = raw_last_24h
        
        # Extract layer diagnostics (ETAP 3) - check extracted_at column exists
        try:
            total_extracted_24h = db.query(IntelExtractedItem).filter(
                IntelExtractedItem.extracted_at >= cutoff_time
            ).count()
        except Exception as e:
            if "extracted_at" in str(e).lower() or "column" in str(e).lower():
                logger.error("[INTEL][EXTRACT] CRITICAL: extracted_at column missing! Run migration 016: alembic upgrade head")
                raise RuntimeError("extracted_at column missing - migration 016 not applied") from e
            raise
        
        extraction_ratio = (total_extracted_24h / total_raw_24h * 100) if total_raw_24h > 0 else 0.0
        
        # Warn if extraction ratio < 5%
        if extraction_ratio < 5.0 and total_raw_24h > 0:
            logger.warning(f"[INTEL][EXTRACT] Low extraction ratio: {extraction_ratio:.2f}% (target: ≥5%)")
        
        # Daily window diagnostics (ETAP 5)
        from zoneinfo import ZoneInfo
        import os
        daily_tz = ZoneInfo(os.getenv("INTEL_DAILY_RUN_TZ", "Europe/Madrid"))
        cutoff_time_str = cutoff_time.isoformat()
        daily_window_hours = 24
        
        # Count relevant items (from extracted meta, not events)
        relevant_count = 0
        for raw_item in raw_items:
            extracted = db.query(IntelExtractedItem).filter(
                IntelExtractedItem.raw_item_id == raw_item.id
            ).first()
            if extracted and extracted.meta and extracted.meta.get("relevance_score", 0) >= 20:
                relevant_count += 1
        
        # Count translated items
        translated_count = 0
        for event in events:
            if event.llm_meta and event.llm_meta.get("translation_applied"):
                translated_count += 1
        
        # Scoring breakdown summary (SIGNIFICANCE AUDIT)
        scoring_stats = {}
        if events:
            scores = [e.significance_score for e in events if e.significance_score]
            if scores:
                zero_scores_count = len([s for s in scores if s == 0])
                scoring_stats = {
                    "min": min(scores),
                    "max": max(scores),
                    "avg": round(sum(scores) / len(scores), 2),
                    "count": len(scores),
                    "zero_scores": zero_scores_count
                }
                
                # ERROR if zero_scores > 0
                if zero_scores_count > 0:
                    logger.error(f"[INTEL][SCORE] CRITICAL: Found {zero_scores_count} events with score=0 (baseline should be ≥25)")
        
        # Scoring breakdown summary (alias for compatibility)
        scoring_breakdown_summary = scoring_stats
        
        # Group errors by domain and status code for diagnostics
        error_breakdown = {}
        for error_info in sources_with_errors:
            error_code = error_info.get("error_code", "unknown")
            source_name = error_info.get("source", "unknown")
            domain = source_name.split(" - ")[-1] if " - " in source_name else source_name
            
            if error_code not in error_breakdown:
                error_breakdown[error_code] = []
            error_breakdown[error_code].append(domain)
        
        # Diagnostic: why 0 new items?
        diagnostic_info = {}
        if extracted_count == 0:
            # Check if raw items exist
            raw_count_24h = db.query(IntelRawItem).filter(
                IntelRawItem.fetched_at >= cutoff_time
            ).count()
            diagnostic_info["raw_items_24h"] = raw_count_24h
            diagnostic_info["extraction_failure_reason"] = "no_raw_items" if raw_count_24h == 0 else "extraction_failed"
        
        if relevant_count == 0 and extracted_count > 0:
            # Check relevance scores distribution
            relevance_scores = []
            for raw_item in raw_items[:100]:  # Sample first 100
                extracted = db.query(IntelExtractedItem).filter(
                    IntelExtractedItem.raw_item_id == raw_item.id
                ).first()
                if extracted and extracted.meta:
                    score = extracted.meta.get("relevance_score", 0)
                    relevance_scores.append(score)
            
            if relevance_scores:
                diagnostic_info["relevance_scores_sample"] = {
                    "min": min(relevance_scores),
                    "max": max(relevance_scores),
                    "avg": sum(relevance_scores) / len(relevance_scores),
                    "above_threshold": len([s for s in relevance_scores if s >= 20])
                }
            diagnostic_info["relevance_failure_reason"] = "all_below_threshold"
        
        if eligible_count == 0 and events_created > 0:
            # Check significance scores distribution
            sig_scores = [e.significance_score for e in events if e.significance_score]
            if sig_scores:
                diagnostic_info["significance_scores"] = {
                    "min": min(sig_scores),
                    "max": max(sig_scores),
                    "avg": sum(sig_scores) / len(sig_scores),
                    "above_threshold": len([s for s in sig_scores if s >= min_score])
                }
            diagnostic_info["eligibility_failure_reason"] = "all_below_score_threshold"
        
        # Determine why published = 0 (E: "Why published=0" diagnostics)
        published_reason = None
        if published_count == 0:
            if collected_count == 0:
                published_reason = "no_sources"
            elif extracted_count == 0:
                published_reason = "collected_zero"
            elif relevant_count == 0:
                published_reason = "no_relevant"
            elif eligible_count == 0:
                published_reason = "no_eligible"
            elif skip_breakdown.get("rate_limited", 0) > 0:
                published_reason = "rate_limited"
            elif skip_breakdown.get("already_published", 0) > 0:
                published_reason = "already_published"
            elif skip_breakdown.get("translation_failed", 0) > 0:
                published_reason = "translation_failed"
            elif skip_breakdown.get("russian_check_failed", 0) > 0:
                published_reason = "russian_check_failed"
            elif skip_breakdown.get("error", 0) > 0:
                published_reason = "error"
            else:
                published_reason = "other"
        else:
            published_reason = "success"
        
        # Publish audit diagnostics
        publish_attempted = eligible_count
        publish_success = published_count
        publish_skipped = skipped_count
        skip_reasons = skip_breakdown.copy()
        
        result = {
            # Collect stage audit (ARCHITECTURE FIX)
            "collect_stage_executed": collect_stage_executed,
            "collect_reason": collect_reason,
            "sources_used": len(sources) if sources else 0,
            "collected": collected_count,
            "saved": raw_saved,  # Actual saved count
            "raw_saved": raw_saved,
            "raw_duplicates": raw_duplicates,
            "sources_processed": len(sources_processed),
            "sources_failed": len(sources_with_errors),
            "sources_with_errors": sources_with_errors,
            "error_breakdown": error_breakdown,
            "items_per_source": items_per_source,
            
            # Raw layer audit
            "raw_last_24h": raw_last_24h,
            "raw_last_6h": raw_last_6h,
            "raw_per_source": raw_per_source,
            "total_raw": total_raw_24h,
            
            # Extract layer audit
            "extracted_last_24h": total_extracted_24h,
            "extraction_ratio": round(extraction_ratio, 2),
            "extracted": extracted_count,
            
            # Events
            "events_created": events_created,
            "relevant_count": relevant_count,
            "translated_count": translated_count,
            "eligible_count": eligible_count,
            
            # Significance audit
            "scoring_stats": scoring_stats,
            "scoring_breakdown_summary": scoring_breakdown_summary,  # Alias
            
            # Daily window logic
            "cutoff_time_used": cutoff_time_str,
            "daily_window_hours": daily_window_hours,
            
            # Briefs and publish
            "briefs_generated": briefs_generated,
            "publish_attempted": publish_attempted,
            "publish_success": publish_success,
            "publish_skipped": publish_skipped,
            "skip_reasons": skip_reasons,
            "skip_breakdown": skip_breakdown,  # Alias
            "published": published_count,
            "skipped": skipped_count,
            "published_reason": published_reason,
            
            # Diagnostics
            "diagnostic_info": diagnostic_info,
            "dry_run": dry_run
        }
        
        logger.info(f"Pipeline complete: collected={collected_count}, relevant={relevant_count}, eligible={eligible_count}, published={published_count}")
        
        return result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()
