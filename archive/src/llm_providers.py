"""
LLM Provider abstraction for OpenAI Responses API and Ollama Chat API
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import httpx
from openai import OpenAI


logger = logging.getLogger(__name__)


class Topic(BaseModel):
    topic: str
    summary: str
    participants: List[str]


class PersonUpdate(BaseModel):
    person: str
    update: str


class CalendarEvent(BaseModel):
    event: str
    date: str
    time: Optional[str] = None


class DigestStructure(BaseModel):
    urgent: List[str]
    decisions: List[str]
    topics: List[Topic]
    people_updates: List[PersonUpdate]
    calendar: List[CalendarEvent]
    unanswered_mentions: List[str]


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    @abstractmethod
    async def generate_digest(self, messages_text: str, system_prompt: str) -> Dict[str, Any]:
        """Generate a digest from messages using the LLM"""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate provider configuration"""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI Responses API provider"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.client = OpenAI(
            api_key=config.get('api_key')  # Will use OPENAI_API_KEY env var if not provided
        )
        self.model = config.get('model', 'gpt-4.1')
        self.max_tokens = config.get('max_tokens', 2000)
        self.temperature = config.get('temperature', 0.3)
    
    async def generate_digest(self, messages_text: str, system_prompt: str) -> Dict[str, Any]:
        """Generate digest using OpenAI Responses API"""
        import time
        request_id = f"openai_{int(time.time())}"
        
        try:
            # Format the complete input for the Responses API
            input_text = f"""{system_prompt}

{messages_text}

Respond with valid JSON matching the required schema."""

            # Log request details
            logger.info(f"[{request_id}] Sending request to OpenAI model {self.model}")
            logger.debug(f"[{request_id}] Request input length: {len(input_text)} characters")
            logger.debug(f"[{request_id}] Request input preview: {input_text[:500]}...")
            
            import time
            start_time = time.time()
            
            response = self.client.responses.parse(
                model=self.model,
                input=input_text,
                text_format=DigestStructure
            )
            
            # Log response details
            processing_time = time.time() - start_time
            logger.info(f"[{request_id}] OpenAI structured response received in {processing_time:.2f} seconds")
            logger.debug(f"[{request_id}] Response ID: {response.id}")
            logger.debug(f"[{request_id}] Response status: {response.status}")
            
            # Log token usage
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                logger.info(f"[{request_id}] Token usage - Input: {usage.input_tokens}, Output: {usage.output_tokens}, Total: {usage.total_tokens}")
            
            # Log model info
            if hasattr(response, 'model'):
                logger.debug(f"[{request_id}] Actual model used: {response.model}")
            
            # Get the structured output
            parsed_result = response.output_parsed
            logger.info(f"[{request_id}] Successfully received structured OpenAI response")
            
            # Convert Pydantic model to dict
            result = parsed_result.model_dump()
            logger.debug(f"[{request_id}] Parsed JSON keys: {list(result.keys())}")
            return result
                
        except Exception as e:
            logger.error(f"[{request_id}] Error calling OpenAI API: {e}")
            logger.error(f"[{request_id}] Request details - Model: {self.model}, Input length: {len(input_text) if 'input_text' in locals() else 'unknown'}")
            # Return a fallback structure
            return {
                "urgent": [f"Error calling OpenAI API: {str(e)}"],
                "decisions": [],
                "topics": [],
                "people_updates": [],
                "calendar": [],
                "unanswered_mentions": []
            }
    
    def validate_config(self) -> bool:
        """Validate OpenAI configuration"""
        try:
            # Test with a simple request
            test_response = self.client.responses.create(
                model=self.model,
                input="Test connection. Respond with: OK"
            )
            
            # Extract content from response structure
            content = ""
            if hasattr(test_response, 'output') and test_response.output:
                for output_item in test_response.output:
                    if hasattr(output_item, 'type') and output_item.type == 'message' and hasattr(output_item, 'content'):
                        for content_item in output_item.content:
                            if hasattr(content_item, 'type') and content_item.type == 'output_text':
                                content = content_item.text if hasattr(content_item, 'text') else ''
                                break
                        if content:
                            break
            
            return "OK" in content
        except Exception as e:
            logger.error(f"OpenAI config validation failed: {e}")
            return False


class OllamaProvider(LLMProvider):
    """Ollama local API provider"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get('base_url', 'http://localhost:11434')
        self.model = config.get('model', 'llama3.2:latest')
        self.temperature = config.get('temperature', 0.3)
        self.top_p = config.get('top_p', 0.9)
        self.client = httpx.AsyncClient(timeout=300)  # 5 minute timeout for local models
    
    async def generate_digest(self, messages_text: str, system_prompt: str) -> Dict[str, Any]:
        """Generate digest using Ollama Chat API"""
        import time
        request_id = f"ollama_{int(time.time())}"
        
        try:
            # Format request for Ollama's chat endpoint
            request_data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": messages_text
                    }
                ],
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "top_p": self.top_p
                }
            }
            
            # Log request details
            logger.info(f"[{request_id}] Sending request to Ollama model {self.model}")
            logger.debug(f"[{request_id}] Request URL: {self.base_url}/api/chat")
            logger.debug(f"[{request_id}] System prompt length: {len(system_prompt)} characters")
            logger.debug(f"[{request_id}] User messages length: {len(messages_text)} characters")
            logger.debug(f"[{request_id}] Request options: temperature={self.temperature}, top_p={self.top_p}")
            
            start_time = time.time()
            
            response = await self.client.post(
                f"{self.base_url}/api/chat",
                json=request_data
            )
            response.raise_for_status()
            
            # Log response details
            processing_time = time.time() - start_time
            logger.info(f"[{request_id}] Ollama response received in {processing_time:.2f} seconds")
            logger.debug(f"[{request_id}] HTTP status: {response.status_code}")
            
            response_data = response.json()
            content = response_data.get('message', {}).get('content', '')
            
            logger.debug(f"[{request_id}] Response content length: {len(content)} characters")
            logger.debug(f"[{request_id}] Raw response data keys: {list(response_data.keys())}")
            
            # Log additional metrics if available
            if 'eval_duration' in response_data:
                eval_time = response_data['eval_duration'] / 1e9  # Convert to seconds
                logger.info(f"[{request_id}] Model evaluation time: {eval_time:.2f} seconds")
            if 'prompt_eval_duration' in response_data:
                prompt_eval_time = response_data['prompt_eval_duration'] / 1e9
                logger.info(f"[{request_id}] Prompt evaluation time: {prompt_eval_time:.2f} seconds")
            if 'eval_count' in response_data:
                logger.info(f"[{request_id}] Tokens generated: {response_data['eval_count']}")
            
            logger.debug(f"[{request_id}] Response content preview: {content[:500]}...")
            
            # Parse the JSON response
            try:
                result = json.loads(content)
                logger.info(f"[{request_id}] Successfully parsed Ollama response as JSON")
                logger.debug(f"[{request_id}] Parsed JSON keys: {list(result.keys())}")
                return result
            except json.JSONDecodeError as e:
                logger.error(f"[{request_id}] Failed to parse Ollama response as JSON: {e}")
                logger.error(f"[{request_id}] Raw response content: {content}")
                # Return a fallback structure
                return {
                    "urgent": [f"Failed to parse LLM response: {str(e)}"],
                    "decisions": [],
                    "topics": [],
                    "people_updates": [],
                    "calendar": [],
                    "unanswered_mentions": [],
                    "raw_response": content,
                    "_error": f"JSON parsing failed: {str(e)}"
                }
                
        except httpx.HTTPError as e:
            logger.error(f"[{request_id}] HTTP error calling Ollama API: {e}")
            logger.error(f"[{request_id}] Request details - URL: {self.base_url}/api/chat, Model: {self.model}")
            raise
        except Exception as e:
            logger.error(f"[{request_id}] Unexpected error calling Ollama API: {e}")
            logger.error(f"[{request_id}] Request details - Model: {self.model}, Base URL: {self.base_url}")
            raise
    
    def validate_config(self) -> bool:
        """Validate Ollama configuration"""
        try:
            # Test connection and model availability using synchronous HTTP client
            import httpx
            
            with httpx.Client(timeout=30) as sync_client:
                response = sync_client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "Test"}],
                        "stream": False
                    }
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama config validation failed: {e}")
            return False


class LLMManager:
    """Manager class to handle different LLM providers"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = self._create_provider()
    
    def _create_provider(self) -> LLMProvider:
        """Create the appropriate LLM provider based on config"""
        provider_type = self.config.get('provider', 'openai').lower()
        
        if provider_type == 'openai':
            return OpenAIProvider(self.config.get('openai', {}))
        elif provider_type == 'ollama':
            return OllamaProvider(self.config.get('ollama', {}))
        else:
            raise ValueError(f"Unsupported LLM provider: {provider_type}")
    
    async def generate_digest(self, messages_text: str, system_prompt: str) -> Dict[str, Any]:
        """Generate digest using the configured provider"""
        return await self.provider.generate_digest(messages_text, system_prompt)
    
    def validate_config(self) -> bool:
        """Validate the current provider configuration"""
        return self.provider.validate_config()
    
    def get_provider_info(self) -> Dict[str, str]:
        """Get information about the current provider"""
        provider_type = self.config.get('provider', 'unknown')
        
        if provider_type == 'openai':
            model = self.config.get('openai', {}).get('model', 'unknown')
        elif provider_type == 'ollama':
            model = self.config.get('ollama', {}).get('model', 'unknown')
        else:
            model = 'unknown'
        
        return {
            'provider': provider_type,
            'model': model
        }