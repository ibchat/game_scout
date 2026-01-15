"""
LLM Client - единый интерфейс для Anthropic/OpenAI
"""
import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting multiple providers"""
    
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "anthropic")
        self.model = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
        
        if self.provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set")
            
            # Import только когда нужно
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ValueError("anthropic package not installed")
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
    
    def generate(
        self, 
        prompt: str, 
        max_tokens: int = 2000,
        temperature: float = 0.3
    ) -> Optional[str]:
        """Generate response from LLM"""
        try:
            if self.provider == "anthropic":
                return self._generate_anthropic(prompt, max_tokens, temperature)
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
                
        except Exception as e:
            logger.error(f"LLM generation error: {e}", exc_info=True)
            return None
    
    def _generate_anthropic(
        self, 
        prompt: str, 
        max_tokens: int,
        temperature: float
    ) -> Optional[str]:
        """Generate using Anthropic Claude"""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            if message.content and len(message.content) > 0:
                return message.content[0].text
            
            return None
            
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return None
    
    def generate_json(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.3
    ) -> Optional[Dict[Any, Any]]:
        """Generate JSON response from LLM"""
        response = self.generate(prompt, max_tokens, temperature)
        
        if not response:
            return None
        
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            
            response = response.strip()
            return json.loads(response)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            return None


def get_llm_client() -> Optional[LLMClient]:
    """
    Get LLM client instance
    Returns None if API key not configured (не выбрасывает ошибку!)
    """
    try:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            logger.info("LLM API key not configured, LLM features will be skipped")
            return None
        
        return LLMClient()
    except Exception as e:
        logger.warning(f"LLM client not available: {e}")
        return None
