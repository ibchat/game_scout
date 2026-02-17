"""
VOY GPT Integration - Controlled ChatGPT interaction
"""
import logging
import json
import os
from typing import Dict, Any, Optional, List
import requests

logger = logging.getLogger(__name__)

# GPT API configuration
GPT_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
GPT_API_KEY = os.getenv("OPENAI_API_KEY", "")
GPT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")


class VoyGPTService:
    """Service for controlled GPT interactions in VOY"""
    
    @staticmethod
    def build_prompt(
        feedback_type: str,
        feedback_reason: Optional[str],
        active_skills: List[Dict[str, float]],
        frozen_skills: List[str],
        max_weight_delta: float,
        min_skill_weight: float,
        max_skill_weight: float
    ) -> str:
        """
        Build GPT prompt using strict template.
        """
        # Format active skills
        active_skills_text = "\n".join([
            f"{skill['key']} (weight={skill['weight']})"
            for skill in active_skills
        ])
        
        # Format frozen skills
        frozen_skills_text = ", ".join(frozen_skills) if frozen_skills else "none"
        
        prompt = f"""SYSTEM:
You are an analytical assistant helping a game scouting system.
You MUST NOT propose new skills.
You MUST NOT change architecture.
You MUST stay within provided limits.
You MUST respond ONLY in valid JSON.

CONTEXT:
User feedback: {feedback_type}
Reason: {feedback_reason or 'No reason provided'}

Active skills:
{active_skills_text}

Frozen skills:
{frozen_skills_text}

Limits:
- max_weight_delta: {max_weight_delta}
- min_weight: {min_skill_weight}
- max_weight: {max_skill_weight}

QUESTION:
Which of the active skills might be over- or under-weighted?
Return ONLY weight adjustments within limits."""
        
        return prompt
    
    @staticmethod
    def validate_gpt_response(
        response_json: Dict[str, Any],
        valid_skill_keys: List[str],
        frozen_skills: List[str],
        max_weight_delta: float,
        min_skill_weight: float,
        max_skill_weight: float
    ) -> tuple[bool, List[Dict[str, Any]]]:
        """
        Validate GPT response strictly.
        Returns: (is_valid, suggestions_list)
        """
        if not isinstance(response_json, dict):
            logger.warning("GPT response is not a dict")
            return False, []
        
        if "suggestions" not in response_json:
            logger.warning("GPT response missing 'suggestions' key")
            return False, []
        
        suggestions = response_json["suggestions"]
        if not isinstance(suggestions, list):
            logger.warning("GPT suggestions is not a list")
            return False, []
        
        valid_suggestions = []
        
        for suggestion in suggestions:
            if not isinstance(suggestion, dict):
                logger.warning(f"Invalid suggestion format: {suggestion}")
                continue
            
            skill = suggestion.get("skill")
            delta = suggestion.get("delta")
            reason = suggestion.get("reason", "")
            
            # Validate skill exists and is not frozen
            if not skill or skill not in valid_skill_keys:
                logger.warning(f"Unknown or invalid skill: {skill}")
                continue
            
            if skill in frozen_skills:
                logger.warning(f"Skill {skill} is frozen, ignoring")
                continue
            
            # Validate delta
            if not isinstance(delta, (int, float)):
                logger.warning(f"Invalid delta type: {delta}")
                continue
            
            if abs(delta) > max_weight_delta:
                logger.warning(f"Delta {delta} exceeds max_weight_delta {max_weight_delta}")
                continue
            
            valid_suggestions.append({
                "skill": skill,
                "delta": float(delta),
                "reason": reason
            })
        
        return len(valid_suggestions) > 0, valid_suggestions
    
    @staticmethod
    def call_gpt(prompt: str) -> Optional[Dict[str, Any]]:
        """
        Call GPT API with prompt.
        Returns parsed JSON or None on error.
        """
        if not GPT_API_KEY:
            logger.warning("OPENAI_API_KEY not set, skipping GPT call")
            return None
        
        try:
            headers = {
                "Authorization": f"Bearer {GPT_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": GPT_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that responds only in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "response_format": {"type": "json_object"}
            }
            
            response = requests.post(GPT_API_URL, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not content:
                logger.warning("Empty GPT response")
                return None
            
            # Parse JSON
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GPT JSON response: {e}")
            return None
        except requests.RequestException as e:
            logger.error(f"GPT API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error calling GPT: {e}", exc_info=True)
            return None
