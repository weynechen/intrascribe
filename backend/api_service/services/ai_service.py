"""
AI services integrated into main API service.
Handles AI-powered tasks like summarization and title generation using LiteLLM.
"""
import os
import sys
import time
import asyncio
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# Add shared components to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from shared.logging import ServiceLogger
from shared.config import get_ai_config

logger = ServiceLogger("ai-service")


@dataclass
class ModelConfig:
    """AI模型配置数据类"""
    name: str
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    max_tokens: int = 2000
    temperature: float = 0.7
    priority: int = 1
    enabled: bool = True


class AIService:
    """
    AI service for text processing tasks.
    Integrates multiple LLM providers using LiteLLM with configuration from ai_config.yaml.
    """
    
    def __init__(self):
        self.config = get_ai_config()
        self.models: List[ModelConfig] = []
        self.retry_config = self.config.get("retry", {})
        self.fallback_config = self.config.get("fallback", {})
        self.prompts_config = self.config.get("prompts", {})
        
        # Initialize models from config
        self._init_models()
        
        # Configure LiteLLM
        self._configure_litellm()
    
    def _init_models(self):
        """Initialize models from configuration"""
        logger.info("Initializing AI models from configuration...")
        
        ai_summary_config = self.config.get("ai_summary", {})
        models_config = ai_summary_config.get("models", [])
        
        for model_config in models_config:
            if model_config.get("enabled", True):
                # Replace environment variable placeholders
                api_key = model_config.get("api_key", "")
                if api_key.startswith("${") and api_key.endswith("}"):
                    env_var = api_key[2:-1]
                    api_key = os.environ.get(env_var, "")
                
                self.models.append(ModelConfig(
                    name=model_config["name"],
                    model=model_config["model"],
                    api_key=api_key if api_key else None,
                    api_base=model_config.get("api_base"),
                    max_tokens=model_config.get("max_tokens", 2000),
                    temperature=model_config.get("temperature", 0.7),
                    priority=model_config.get("priority", 1),
                    enabled=model_config.get("enabled", True)
                ))
        
        # Sort by priority
        self.models.sort(key=lambda x: x.priority)
        
        if self.models:
            logger.info(f"Loaded {len(self.models)} AI model configurations")
            for model in self.models:
                logger.info(f"  - {model.name}: {model.model} (priority: {model.priority})")
        else:
            logger.warning("No available AI model configurations found")
    
    def _configure_litellm(self):
        """Configure LiteLLM"""
        try:
            import litellm
            
            # Set log level
            litellm.set_verbose = False
            
            # Set timeout from config
            timeout = self.retry_config.get("timeout", 5)
            litellm.request_timeout = timeout
            
            logger.info("LiteLLM configuration completed")
        except ImportError:
            logger.warning("LiteLLM not available - install with: pip install litellm")
    
    def is_available(self) -> bool:
        """Check if any AI models are available"""
        return len([m for m in self.models if m.enabled]) > 0
    
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
        if not transcription_text.strip():
            return {
                "success": False,
                "summary": "转录内容为空，无法生成总结。",
                "error_message": "empty_transcription"
            }
        
        if not self.is_available():
            return await self._handle_fallback(transcription_text)
        
        start_time = time.time()
        
        # Build prompts from configuration
        ai_summary_config = self.config.get("ai_summary", {})
        base_system_prompt = ai_summary_config.get("prompts", {}).get("system_prompt", 
            "你是一个专业的会议记录助手，擅长分析会议转录内容并生成结构化的总结。")
        
        if template_content:
            # Use template in system prompt for better role definition
            system_prompt = f"""{base_system_prompt}

你需要严格按照以下模板格式进行总结。请注意：
1. 模板是纯文本结构化描述，描述了期望的输出格式和内容要求
2. 请严格遵循模板的结构和格式，用实际内容填充各个部分
3. 保持模板的markdown格式和层次结构
4. 如果某些信息在转录中没有明确提及，可以标注为"未提及"或根据上下文合理推断
5. 确保输出内容完整、准确、结构清晰

输出格式模板：
{template_content}"""
            
            user_prompt = f"请按照系统提示中的模板格式，对以下转录内容进行结构化总结：\n\n{transcription_text}。\n\n以上为内容，请按照模板格式进行总结。"
        else:
            # Use default prompts from config
            system_prompt = base_system_prompt
            user_prompt_template = ai_summary_config.get("prompts", {}).get("user_prompt_template", 
                "请对以下会议转录内容进行总结：\n\n转录内容：\n{transcription}\n\n请生成一份结构化的会议总结，包含关键要点、行动项目、重要决策等内容。")
            user_prompt = user_prompt_template.format(transcription=transcription_text)
        
        # Try each model in priority order
        for model_config in self.models:
            try:
                logger.info(f"Attempting summary with model: {model_config.name}")
                
                summary, metadata = await self._call_model(
                    model_config, system_prompt, user_prompt
                )
                
                if summary:
                    processing_time = int((time.time() - start_time) * 1000)
                    
                    # Extract key points if possible
                    key_points = self._extract_key_points(summary)
                    
                    metadata.update({
                        "model_used": model_config.name,
                        "ai_model": model_config.model,
                        "ai_provider": model_config.name.split()[0].lower(),
                        "success": True,
                        "processing_time_ms": processing_time
                    })
                    
                    logger.success(f"Summary generated successfully with {model_config.name}")
                    
                    return {
                        "success": True,
                        "summary": summary,
                        "key_points": key_points,
                        "processing_time_ms": processing_time,
                        "model_used": model_config.name,
                        "ai_model": model_config.model,
                        "ai_provider": model_config.name.split()[0].lower(),
                        "token_usage": metadata.get("token_usage", {}),
                        "cost_cents": metadata.get("cost_cents", 0)
                    }
                    
            except Exception as e:
                logger.warning(f"Model {model_config.name} failed: {e}")
                continue
        
        # All models failed, use fallback
        return await self._handle_fallback(transcription_text)
    
    async def generate_title(self, transcription: str, summary: str = None) -> Dict[str, Any]:
        """
        Generate title for transcription.
        
        Args:
            transcription: Original transcription text
            summary: Optional summary to help with title generation
        
        Returns:
            Dictionary with title results
        """
        if not transcription.strip():
            return {
                "success": False,
                "title": "无标题内容",
                "error_message": "empty_transcription"
            }
        
        if not self.is_available():
            return await self._handle_title_fallback(transcription)
        
        start_time = time.time()
        
        # Build prompts for title generation
        system_prompt = "你是一个专业的会议记录助手，负责为会议内容生成简洁明了的标题。"
        
        if summary:
            # Use summary and transcription for better title generation
            user_prompt = f"""请基于以下会议总结和转录内容，生成一个简洁明了的标题（10-15个字）：

总结内容：
{summary}

转录内容：
{transcription[:500]}...

要求：
1. 标题要能准确概括会议的主要内容和目的
2. 长度控制在10-15个字
3. 直接返回标题，不要其他解释
4. 使用中文
"""
        else:
            # Use transcription only
            user_prompt = f"""请基于以下会议转录内容，生成一个简洁明了的标题（10-15个字）：

转录内容：
{transcription[:500]}...

要求：
1. 标题要能准确概括会议的主要内容和目的
2. 长度控制在10-15个字
3. 直接返回标题，不要其他解释
4. 使用中文
"""
        
        # Try each model in priority order
        for model_config in self.models:
            try:
                logger.info(f"Attempting title generation with model: {model_config.name}")
                
                title, metadata = await self._call_model(
                    model_config, system_prompt, user_prompt
                )
                
                if title:
                    # Clean up title
                    title = title.strip().replace('"', '').replace("'", "")
                    # Truncate if too long
                    if len(title) > 20:
                        title = title[:17] + "..."
                    
                    processing_time = int((time.time() - start_time) * 1000)
                    
                    metadata.update({
                        "model_used": model_config.name,
                        "ai_model": model_config.model,
                        "success": True,
                        "title_type": "summary_based" if summary else "transcription_based",
                        "processing_time_ms": processing_time
                    })
                    
                    logger.success(f"Title generated successfully with {model_config.name}: {title}")
                    
                    return {
                        "success": True,
                        "title": title,
                        "processing_time_ms": processing_time,
                        "model_used": model_config.name
                    }
                    
            except Exception as e:
                logger.warning(f"Model {model_config.name} failed: {e}")
                continue
        
        # All models failed, use fallback
        return await self._handle_title_fallback(transcription)
    
    async def _call_model(self, model_config: ModelConfig, system_prompt: str, user_prompt: str) -> Tuple[str, Dict[str, Any]]:
        """
        Call a specific LLM model.
        
        Args:
            model_config: Model configuration object
            system_prompt: System prompt
            user_prompt: User prompt
        
        Returns:
            Tuple of (response_text, metadata)
        """
        start_time = time.time()
        
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
                "model": model_config.model,
                "messages": messages,
                "max_tokens": model_config.max_tokens,
                "temperature": model_config.temperature,
            }
            
            # Set API key and base URL based on model configuration
            if model_config.api_key:
                # Set environment variables based on model type
                if "openai" in model_config.model.lower() or "gpt" in model_config.model.lower():
                    os.environ["OPENAI_API_KEY"] = model_config.api_key
                elif "claude" in model_config.model.lower() or "anthropic" in model_config.model.lower():
                    os.environ["ANTHROPIC_API_KEY"] = model_config.api_key
                elif "deepseek" in model_config.model.lower():
                    os.environ["DEEPSEEK_API_KEY"] = model_config.api_key
                elif "qwen" in model_config.model.lower():
                    os.environ["QWEN_API_KEY"] = model_config.api_key
            
            if model_config.api_base:
                kwargs["api_base"] = model_config.api_base
            
            # Make API call with retry logic
            response = await self._call_with_retry(acompletion, **kwargs)
            
            # Extract response content
            content = response.choices[0].message.content
            
            # Clean the response
            content = self._clean_llm_response(content)
            
            # Calculate processing time
            processing_time = (time.time() - start_time) * 1000
            
            # Build metadata with cost calculation
            metadata = {
                "total_processing_time": processing_time,
                "transcription_length": len(user_prompt),
                "timestamp": int(time.time()),
                "tokens_used": getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0,
            }
            
            # Add cost information - handle LiteLLM cost calculation
            try:
                cost_usd = None
                
                # Try to get cost from various LiteLLM response attributes
                if hasattr(response, '_response_ms') and response._response_ms:
                    cost_usd = response._response_ms
                elif hasattr(response, 'cost'):
                    cost_usd = response.cost
                elif hasattr(response, '_response_cost_usd'):
                    cost_usd = response._response_cost_usd
                elif hasattr(response, 'usage') and hasattr(response.usage, 'cost'):
                    cost_usd = response.usage.cost
                elif hasattr(response, 'usage') and hasattr(response.usage, 'total_cost'):
                    cost_usd = response.usage.total_cost
                
                # Convert USD to cents and ensure it's an integer
                if cost_usd is not None:
                    cost_cents = round(float(cost_usd) * 100)
                    metadata["cost_cents"] = cost_cents
                    logger.info(f"💰 Cost calculation: {cost_usd} USD = {cost_cents} cents")
                else:
                    metadata["cost_cents"] = 0
                    logger.debug("💰 No cost information found, setting to 0")
                    
            except Exception as e:
                logger.warning(f"💰 Cost calculation failed: {e}")
                metadata["cost_cents"] = 0
            
            # Add token usage details
            if hasattr(response, 'usage'):
                metadata["token_usage"] = {
                    "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                    "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
                    "total_tokens": getattr(response.usage, 'total_tokens', 0)
                }
            
            return content, metadata
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            metadata = {
                "error": str(e),
                "total_processing_time": processing_time,
                "timestamp": int(time.time()),
            }
            raise Exception(f"Model call failed: {e}")
    
    async def _call_with_retry(self, func, **kwargs):
        """Call function with exponential backoff retry"""
        max_attempts = self.retry_config.get("max_attempts", 3)
        backoff_factor = self.retry_config.get("backoff_factor", 2)
        timeout = self.retry_config.get("timeout", 30)
        
        for attempt in range(max_attempts):
            try:
                return await func(**kwargs)
            except Exception as e:
                if attempt == max_attempts - 1:
                    raise e
                
                # Calculate delay with exponential backoff
                delay = min(backoff_factor ** attempt, timeout)
                
                logger.warning(f"API call failed (attempt {attempt + 1}/{max_attempts}), retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
    
    async def _handle_fallback(self, transcription: str) -> Dict[str, Any]:
        """
        Handle fallback strategy for summary generation.
        
        Args:
            transcription: Transcription text
            
        Returns:
            Fallback summary response
        """
        if self.fallback_config.get("mock_response", False):
            # Generate mock summary
            mock_summary = self._generate_mock_summary(transcription)
            
            return {
                "success": True,
                "summary": mock_summary,
                "key_points": [],
                "processing_time_ms": 0,
                "model_used": "fallback",
                "ai_model": "mock",
                "ai_provider": "fallback",
                "token_usage": {},
                "cost_cents": 0,
                "fallback_used": True
            }
        else:
            return {
                "success": False,
                "summary": "",
                "error_message": "All AI models failed and fallback is disabled"
            }
    
    async def _handle_title_fallback(self, transcription: str) -> Dict[str, Any]:
        """
        Handle fallback strategy for title generation.
        
        Args:
            transcription: Transcription text
            
        Returns:
            Fallback title response
        """
        if self.fallback_config.get("mock_response", False):
            # Generate time-based default title
            now = datetime.now()
            default_title = f"会议记录 {now.strftime('%Y-%m-%d %H:%M')}"
            
            return {
                "success": True,
                "title": default_title,
                "processing_time_ms": 0,
                "model_used": "fallback",
                "fallback_used": True
            }
        else:
            return {
                "success": False,
                "title": "",
                "error_message": "All AI models failed and fallback is disabled"
            }
    
    def _generate_mock_summary(self, transcription: str) -> str:
        """
        Generate rule-based simple summary.
        
        Args:
            transcription: Transcription text
            
        Returns:
            Simple summary text
        """
        # Simple text analysis
        word_count = len(transcription.split())
        char_count = len(transcription)
        
        # Extract keywords
        keywords = []
        common_words = ['会议', '讨论', '决定', '计划', '项目', '方案', '问题', '解决', '目标', '时间']
        for word in common_words:
            if word in transcription:
                keywords.append(word)
        
        # Build simple summary
        summary_parts = [
            f"本次会议/对话共包含约 {word_count} 个词，{char_count} 个字符。"
        ]
        
        if keywords:
            summary_parts.append(f"主要涉及：{', '.join(keywords[:5])}等话题。")
        
        # Extract first few sentences as content overview
        sentences = transcription.split('。')[:3]
        if sentences:
            content_preview = '。'.join(sentences)[:200] + "..."
            summary_parts.append(f"内容概述：{content_preview}")
        
        return "\n\n".join(summary_parts)
    
    def _clean_llm_response(self, content: str) -> str:
        """
        Clean LLM response content.
        
        Args:
            content: Raw response content
            
        Returns:
            Cleaned content
        """
        if not content:
            return ""
        
        # Remove extra whitespace
        content = content.strip()
        
        # Remove possible markdown formatting
        content = re.sub(r'^```.*?\n', '', content, flags=re.MULTILINE)
        content = re.sub(r'\n```$', '', content)
        
        # Remove excessive newlines
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Remove <think> and </think> tags
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        
        return content
    
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
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models"""
        return [
            {
                "name": model.name,
                "model": model.model,
                "enabled": model.enabled,
                "priority": model.priority
            }
            for model in self.models
        ]
    
    def get_config_status(self) -> Dict[str, Any]:
        """Get configuration status"""
        return {
            "total_models": len(self.models),
            "enabled_models": len([m for m in self.models if m.enabled]),
            "has_fallback": bool(self.fallback_config),
            "retry_config": self.retry_config,
            "fallback_config": self.fallback_config
        }


# Global AI service instance
ai_service = AIService()
