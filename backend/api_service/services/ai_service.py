"""
AI services integrated into main API service.
Handles AI-powered tasks like summarization and title generation using LiteLLM.
"""
import os
import sys
import time
import asyncio
from typing import Dict, Any, List, Optional, Tuple

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import ai_config

logger = ServiceLogger("ai-service")


class AIService:
    """
    AI service for text processing tasks.
    Integrates multiple LLM providers using LiteLLM.
    """
    
    def __init__(self):
        self.models = []
        self.retry_config = {
            "max_retries": 3,
            "base_delay": 1.0,
            "max_delay": 60.0
        }
        self.prompts = {
            "system_prompt": "You are a professional meeting summarizer. Provide clear, structured summaries in Markdown format. Always respond in Chinese.",
            "summary_template": "Please summarize the following meeting transcript:\n\n{transcription}\n\nProvide a structured summary with key points and action items in Chinese.",
            "title_template": "Generate a concise, descriptive title in Chinese for this meeting based on the content:\n\n{transcription}\n\nTitle:"
        }
        
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize available LLM models"""
        logger.info("Initializing AI models...")
        
        self.models = []
        
        # OpenAI models
        if ai_config.openai_api_key:
            self.models.extend([
                {
                    "name": "OpenAI GPT-3.5",
                    "model": "gpt-3.5-turbo",
                    "api_key": ai_config.openai_api_key,
                    "priority": 1,
                    "enabled": True
                },
                {
                    "name": "OpenAI GPT-4",
                    "model": "gpt-4",
                    "api_key": ai_config.openai_api_key,
                    "priority": 2,
                    "enabled": True
                }
            ])
        
        # Anthropic models
        if ai_config.anthropic_api_key:
            self.models.append({
                "name": "Claude 3 Haiku",
                "model": "claude-3-haiku-20240307",
                "api_key": ai_config.anthropic_api_key,
                "priority": 3,
                "enabled": True
            })
        
        # Sort by priority
        self.models.sort(key=lambda x: x["priority"])
        
        enabled_models = [m["name"] for m in self.models if m["enabled"]]
        logger.info(f"Initialized {len(enabled_models)} AI models: {enabled_models}")
        
        if not enabled_models:
            logger.warning("No AI models available - API keys may be missing")
    
    def is_available(self) -> bool:
        """Check if any AI models are available"""
        return len([m for m in self.models if m["enabled"]]) > 0
    
    async def generate_summary(
        self, 
        transcription_text: str, 
        session_id: str, 
        template_content: str = None
    ) -> Dict[str, Any]:
        """
        Generate AI summary for transcription text.
        
        Args:
            transcription_text: Text to summarize
            session_id: Session ID for logging
            template_content: Optional template for formatting
        
        Returns:
            Dictionary with summary results
        """
        if not self.is_available():
            return {
                "success": False,
                "summary": "",
                "error_message": "No AI models available"
            }
        
        start_time = time.time()
        
        # Build prompt
        system_prompt = self.prompts["system_prompt"]
        if template_content:
            user_prompt = f"Use this template structure:\n{template_content}\n\nTranscript to summarize:\n{transcription_text}"
        else:
            user_prompt = self.prompts["summary_template"].format(
                transcription=transcription_text
            )
        
        # Try each model in priority order
        last_error = None
        for model in self.models:
            if not model["enabled"]:
                continue
            
            try:
                logger.info(f"Attempting summary with model: {model['name']}")
                
                summary, metadata = await self._call_model(
                    model, system_prompt, user_prompt
                )
                
                processing_time = int((time.time() - start_time) * 1000)
                
                # Extract key points if possible
                key_points = self._extract_key_points(summary)
                
                logger.success(f"Summary generated successfully with {model['name']}")
                
                return {
                    "success": True,
                    "summary": summary,
                    "key_points": key_points,
                    "processing_time_ms": processing_time,
                    "model_used": model["name"],
                    "ai_model": model["model"],
                    "ai_provider": model["name"].split()[0].lower()
                }
                
            except Exception as e:
                logger.warning(f"Model {model['name']} failed: {e}")
                last_error = e
                continue
        
        # All models failed
        processing_time = int((time.time() - start_time) * 1000)
        error_message = f"All AI models failed. Last error: {last_error}"
        
        logger.error(f"Summary generation failed: {error_message}")
        
        return {
            "success": False,
            "summary": "",
            "processing_time_ms": processing_time,
            "error_message": error_message
        }
    
    async def generate_title(self, transcription: str, summary: str = None) -> Dict[str, Any]:
        """
        Generate title for transcription.
        
        Args:
            transcription: Original transcription text
            summary: Optional summary to help with title generation
        
        Returns:
            Dictionary with title results
        """
        if not self.is_available():
            return {
                "success": False,
                "title": "",
                "error_message": "No AI models available"
            }
        
        start_time = time.time()
        
        # Build prompt for title generation
        system_prompt = "You are a professional meeting title generator. Create concise, descriptive titles in Chinese."
        
        content = summary if summary else transcription
        user_prompt = self.prompts["title_template"].format(transcription=content)
        
        # Try each model in priority order
        last_error = None
        for model in self.models:
            if not model["enabled"]:
                continue
            
            try:
                logger.info(f"Attempting title generation with model: {model['name']}")
                
                title, metadata = await self._call_model(
                    model, system_prompt, user_prompt
                )
                
                # Clean up title (remove quotes, extra whitespace)
                title = title.strip().strip('"\'').strip()
                
                processing_time = int((time.time() - start_time) * 1000)
                
                logger.success(f"Title generated successfully with {model['name']}")
                
                return {
                    "success": True,
                    "title": title,
                    "processing_time_ms": processing_time,
                    "model_used": model["name"]
                }
                
            except Exception as e:
                logger.warning(f"Model {model['name']} failed: {e}")
                last_error = e
                continue
        
        # All models failed
        processing_time = int((time.time() - start_time) * 1000)
        error_message = f"All AI models failed. Last error: {last_error}"
        
        logger.error(f"Title generation failed: {error_message}")
        
        return {
            "success": False,
            "title": "",
            "processing_time_ms": processing_time,
            "error_message": error_message
        }
    
    async def _call_model(self, model_config: Dict, system_prompt: str, user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """
        Call a specific LLM model.
        
        Args:
            model_config: Model configuration
            system_prompt: System prompt
            user_prompt: User prompt
        
        Returns:
            Tuple of (response_text, metadata)
        """
        try:
            # Import litellm for unified API access
            from litellm import acompletion
            
            # Prepare messages
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Prepare API call parameters
            kwargs = {
                "model": model_config["model"],
                "messages": messages,
                "max_tokens": ai_config.max_tokens,
                "temperature": ai_config.temperature,
                "timeout": ai_config.timeout_seconds,
            }
            
            # Set API key based on model type
            if "gpt" in model_config["model"].lower():
                os.environ["OPENAI_API_KEY"] = model_config["api_key"]
            elif "claude" in model_config["model"].lower():
                os.environ["ANTHROPIC_API_KEY"] = model_config["api_key"]
            
            # Make API call with retry logic
            response = await self._call_with_retry(acompletion, **kwargs)
            
            # Extract response content
            content = response.choices[0].message.content
            
            # Build metadata
            metadata = {
                "model": model_config["model"],
                "provider": model_config["name"],
                "usage": getattr(response, 'usage', {}),
            }
            
            return content, metadata
            
        except Exception as e:
            logger.error(f"Model call failed for {model_config['name']}", e)
            raise
    
    async def _call_with_retry(self, func, **kwargs):
        """Call function with exponential backoff retry"""
        max_retries = self.retry_config["max_retries"]
        base_delay = self.retry_config["base_delay"]
        max_delay = self.retry_config["max_delay"]
        
        for attempt in range(max_retries + 1):
            try:
                return await func(**kwargs)
            except Exception as e:
                if attempt == max_retries:
                    raise e
                
                # Calculate delay with exponential backoff
                delay = min(base_delay * (2 ** attempt), max_delay)
                
                logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
    
    def _extract_key_points(self, summary: str) -> List[str]:
        """Extract key points from summary text"""
        try:
            # Simple extraction based on markdown lists or bullet points
            lines = summary.split('\n')
            key_points = []
            
            for line in lines:
                line = line.strip()
                if line.startswith('- ') or line.startswith('* ') or line.startswith('• '):
                    point = line[2:].strip()
                    if point:
                        key_points.append(point)
                elif line.startswith(('1. ', '2. ', '3. ', '4. ', '5. ')):
                    point = line[3:].strip()
                    if point:
                        key_points.append(point)
            
            return key_points[:10]  # Limit to 10 key points
            
        except Exception as e:
            logger.warning(f"Failed to extract key points: {e}")
            return []


# Global AI service instance
ai_service = AIService()
