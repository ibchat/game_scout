"""
Steam Business Brief Generator
Generates structured business briefs from Intel events using LLM.
Strictly follows policy: facts only, no fabrication, Russian language.
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from apps.intel.db.models import IntelEvent, IntelExtractedItem
from apps.intel.policy.policy_engine import load_policy
from apps.intel.policy.policy_brief import get_policy_brief_for_llm
from apps.intel.config import INTEL_LLM_PROVIDER, INTEL_LLM_MODEL_STRONG

logger = logging.getLogger(__name__)


def generate_business_brief(event: IntelEvent, db_session) -> Dict[str, Any]:
    """
    Generate business brief for Intel event.
    
    Returns JSON structure:
    {
      "headline": "...",
      "what_happened": "...",
      "why_it_matters": "...",
      "market_signal": "...",
      "risk_level": "...",
      "confidence": 0.0-1.0
    }
    
    Rules:
    - Only facts from extracted_text
    - No fabrication
    - No numbers if not in source
    - Russian language
    """
    policy = load_policy()
    policy_brief = get_policy_brief_for_llm()
    
    # Get extracted items for this event
    # Event is linked to cluster, cluster has extracted items
    extracted_texts = []
    if event.cluster_id:
        from apps.intel.db.models import IntelCluster
        cluster = db_session.query(IntelCluster).filter(
            IntelCluster.id == event.cluster_id
        ).first()
        
        if cluster:
            extracted_items = db_session.query(IntelExtractedItem).filter(
                IntelExtractedItem.cluster_id == cluster.id
            ).all()
            
            for item in extracted_items:
                if item.extracted_text:
                    extracted_texts.append(item.extracted_text)
    
    # Fallback: use existing event fields
    if not extracted_texts:
        extracted_texts = [event.what_happened_ru or ""]
    
    # Combine extracted text
    source_text = "\n\n".join(extracted_texts[:5])  # Max 5 items
    
    # Build LLM prompt
    prompt = f"""Ты — аналитик игрового рынка. Создай деловой бриф на основе фактов.

ПОЛИТИКА:
{policy_brief}

ИСХОДНЫЕ ДАННЫЕ:
Тип события: {event.event_type}
Название: {event.title_ru}
Что произошло: {event.what_happened_ru}
Почему важно: {event.why_it_matters_ru or "нет данных"}

ИЗВЛЕЧЕННЫЙ ТЕКСТ:
{source_text[:2000]}

ТРЕБОВАНИЯ:
1. Используй ТОЛЬКО факты из исходных данных
2. НЕ придумывай числа, если их нет в источнике
3. Если данных нет — пиши "нет данных"
4. Язык: русский
5. Формат: строго JSON

Верни JSON:
{{
  "headline": "краткий заголовок (до 100 символов)",
  "what_happened": "что произошло (факты из источника)",
  "why_it_matters": "почему это важно для рынка/инвесторов",
  "market_signal": "сигнал рынка (bullish/bearish/neutral)",
  "risk_level": "low/medium/high",
  "confidence": 0.0-1.0
}}"""

    try:
        # Use existing LLM client from worker
        from apps.worker.llm.client import get_llm_client
        
        llm_client = get_llm_client()
        
        if llm_client:
            # Generate JSON response
            brief_json = llm_client.generate_json(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.3
            )
            
            if brief_json:
                # Validate structure
                required_fields = ["headline", "what_happened", "why_it_matters", "market_signal", "risk_level", "confidence"]
                for field in required_fields:
                    if field not in brief_json:
                        brief_json[field] = "нет данных" if field != "confidence" else 0.5
                
                # Validate confidence
                if not isinstance(brief_json["confidence"], (int, float)):
                    brief_json["confidence"] = 0.5
                brief_json["confidence"] = max(0.0, min(1.0, float(brief_json["confidence"])))
                
                return brief_json
        
        # Fallback: return structured data from event
        logger.warning("LLM client not available, using fallback")
        return {
            "headline": event.title_ru[:100],
            "what_happened": event.what_happened_ru,
            "why_it_matters": event.why_it_matters_ru or "нет данных",
            "market_signal": "neutral",
            "risk_level": "medium",
            "confidence": 0.7
        }
            
    except Exception as e:
        logger.error(f"Failed to generate business brief: {e}", exc_info=True)
        # Fallback to event data
        return {
            "headline": event.title_ru[:100],
            "what_happened": event.what_happened_ru,
            "why_it_matters": event.why_it_matters_ru or "нет данных",
            "market_signal": "neutral",
            "risk_level": "medium",
            "confidence": 0.5
        }
