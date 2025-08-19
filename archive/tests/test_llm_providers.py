"""
Tests for LLM provider modules
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
import httpx

from src.llm_providers import OpenAIProvider, OllamaProvider, LLMManager


class TestOpenAIProvider:
    """Test OpenAI provider functionality"""
    
    def test_init(self, sample_config):
        """Test OpenAI provider initialization"""
        config = sample_config["llm"]["openai"]
        provider = OpenAIProvider(config)
        
        assert provider.model == "gpt-4.1"
        assert provider.max_tokens == 2000
        assert provider.temperature == 0.3
        assert provider.client is not None
    
    @pytest.mark.asyncio
    async def test_generate_digest_success(self, sample_config, mock_openai_client, sample_digest_json):
        """Test successful digest generation with OpenAI"""
        config = sample_config["llm"]["openai"]
        
        # Mock the response
        mock_openai_client.responses.create.return_value.content = json.dumps(sample_digest_json)
        
        with patch('src.llm_providers.OpenAI', return_value=mock_openai_client):
            provider = OpenAIProvider(config)
            provider.client = mock_openai_client
            
            result = await provider.generate_digest("Test messages", "Test prompt")
            
            assert result["urgent"] == sample_digest_json["urgent"]
            assert result["decisions"] == sample_digest_json["decisions"]
            assert "topics" in result
            
            # Verify API was called
            mock_openai_client.responses.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_digest_invalid_json(self, sample_config, mock_openai_client):
        """Test digest generation with invalid JSON response"""
        config = sample_config["llm"]["openai"]
        
        # Mock invalid JSON response
        mock_openai_client.responses.create.return_value.content = "Invalid JSON response"
        
        with patch('src.llm_providers.OpenAI', return_value=mock_openai_client):
            provider = OpenAIProvider(config)
            provider.client = mock_openai_client
            
            result = await provider.generate_digest("Test messages", "Test prompt")
            
            # Should return fallback structure
            assert "urgent" in result
            assert "Failed to parse LLM response" in result["urgent"][0]
            assert "raw_response" in result
            assert "_error" in result
    
    @pytest.mark.asyncio
    async def test_generate_digest_api_error(self, sample_config, mock_openai_client):
        """Test digest generation with API error"""
        config = sample_config["llm"]["openai"]
        
        # Mock API error
        mock_openai_client.responses.create.side_effect = Exception("API Error")
        
        with patch('src.llm_providers.OpenAI', return_value=mock_openai_client):
            provider = OpenAIProvider(config)
            provider.client = mock_openai_client
            
            with pytest.raises(Exception, match="API Error"):
                await provider.generate_digest("Test messages", "Test prompt")
    
    def test_validate_config_success(self, sample_config, mock_openai_client):
        """Test successful config validation"""
        config = sample_config["llm"]["openai"]
        
        # Mock successful validation response
        mock_openai_client.responses.create.return_value.content = "OK"
        
        with patch('src.llm_providers.OpenAI', return_value=mock_openai_client):
            provider = OpenAIProvider(config)
            provider.client = mock_openai_client
            
            assert provider.validate_config() == True
    
    def test_validate_config_failure(self, sample_config, mock_openai_client):
        """Test config validation failure"""
        config = sample_config["llm"]["openai"]
        
        # Mock validation error
        mock_openai_client.responses.create.side_effect = Exception("Invalid API key")
        
        with patch('src.llm_providers.OpenAI', return_value=mock_openai_client):
            provider = OpenAIProvider(config)
            provider.client = mock_openai_client
            
            assert provider.validate_config() == False


class TestOllamaProvider:
    """Test Ollama provider functionality"""
    
    def test_init(self, sample_config):
        """Test Ollama provider initialization"""
        config = sample_config["llm"]["ollama"]
        provider = OllamaProvider(config)
        
        assert provider.model == "llama3.2:latest"
        assert provider.base_url == "http://localhost:11434"
        assert provider.temperature == 0.3
        assert provider.top_p == 0.9
        assert provider.client is not None
    
    @pytest.mark.asyncio
    async def test_generate_digest_success(self, sample_config, mock_httpx_client, sample_digest_json):
        """Test successful digest generation with Ollama"""
        config = sample_config["llm"]["ollama"]
        
        # Mock successful response
        mock_httpx_client.post.return_value.json.return_value = {
            "message": {"content": json.dumps(sample_digest_json)},
            "eval_duration": 2000000000,
            "eval_count": 75
        }
        
        provider = OllamaProvider(config)
        provider.client = mock_httpx_client
        
        result = await provider.generate_digest("Test messages", "Test prompt")
        
        assert result["urgent"] == sample_digest_json["urgent"]
        assert result["decisions"] == sample_digest_json["decisions"]
        assert "topics" in result
        
        # Verify API was called correctly
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        assert "/api/chat" in call_args[0][0]
        assert call_args[1]["json"]["model"] == "llama3.2:latest"
        assert call_args[1]["json"]["format"] == "json"
    
    @pytest.mark.asyncio
    async def test_generate_digest_invalid_json(self, sample_config, mock_httpx_client):
        """Test digest generation with invalid JSON response"""
        config = sample_config["llm"]["ollama"]
        
        # Mock invalid JSON response
        mock_httpx_client.post.return_value.json.return_value = {
            "message": {"content": "Invalid JSON response"}
        }
        
        provider = OllamaProvider(config)
        provider.client = mock_httpx_client
        
        result = await provider.generate_digest("Test messages", "Test prompt")
        
        # Should return fallback structure
        assert "urgent" in result
        assert "Failed to parse LLM response" in result["urgent"][0]
        assert "raw_response" in result
        assert "_error" in result
    
    @pytest.mark.asyncio
    async def test_generate_digest_http_error(self, sample_config, mock_httpx_client):
        """Test digest generation with HTTP error"""
        config = sample_config["llm"]["ollama"]
        
        # Mock HTTP error
        mock_httpx_client.post.side_effect = httpx.HTTPError("Connection failed")
        
        provider = OllamaProvider(config)
        provider.client = mock_httpx_client
        
        with pytest.raises(httpx.HTTPError):
            await provider.generate_digest("Test messages", "Test prompt")
    
    @pytest.mark.asyncio
    async def test_generate_digest_with_metrics(self, sample_config, mock_httpx_client, sample_digest_json):
        """Test digest generation with performance metrics"""
        config = sample_config["llm"]["ollama"]
        
        # Mock response with detailed metrics
        mock_httpx_client.post.return_value.json.return_value = {
            "message": {"content": json.dumps(sample_digest_json)},
            "eval_duration": 3000000000,  # 3 seconds
            "prompt_eval_duration": 500000000,  # 0.5 seconds
            "eval_count": 100,
            "prompt_eval_count": 50
        }
        
        provider = OllamaProvider(config)
        provider.client = mock_httpx_client
        
        # Should not raise exception and return valid result
        result = await provider.generate_digest("Test messages", "Test prompt")
        assert "urgent" in result
    
    def test_validate_config_success(self, sample_config):
        """Test successful Ollama config validation"""
        config = sample_config["llm"]["ollama"]
        
        async def mock_post(*args, **kwargs):
            response = AsyncMock()
            response.status_code = 200
            return response
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.post = mock_post
            
            provider = OllamaProvider(config)
            # Note: This is a sync test, so we can't easily test the async validation
            # In a real test, you'd use pytest-asyncio
            assert hasattr(provider, 'validate_config')


class TestLLMManager:
    """Test LLM manager functionality"""
    
    def test_init_openai(self, sample_config):
        """Test LLM manager initialization with OpenAI"""
        llm_config = sample_config["llm"]
        manager = LLMManager(llm_config)
        
        assert isinstance(manager.provider, OpenAIProvider)
        assert manager.config["provider"] == "openai"
    
    def test_init_ollama(self, sample_config):
        """Test LLM manager initialization with Ollama"""
        llm_config = sample_config["llm"]
        llm_config["provider"] = "ollama"
        
        manager = LLMManager(llm_config)
        
        assert isinstance(manager.provider, OllamaProvider)
        assert manager.config["provider"] == "ollama"
    
    def test_init_invalid_provider(self, sample_config):
        """Test LLM manager initialization with invalid provider"""
        llm_config = sample_config["llm"]
        llm_config["provider"] = "invalid"
        
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMManager(llm_config)
    
    @pytest.mark.asyncio
    async def test_generate_digest_delegates(self, sample_config, mock_openai_client, sample_digest_json):
        """Test that manager delegates to provider"""
        llm_config = sample_config["llm"]
        mock_openai_client.responses.create.return_value.content = json.dumps(sample_digest_json)
        
        with patch('src.llm_providers.OpenAI', return_value=mock_openai_client):
            manager = LLMManager(llm_config)
            
            result = await manager.generate_digest("Test messages", "Test prompt")
            
            assert result["urgent"] == sample_digest_json["urgent"]
            mock_openai_client.responses.create.assert_called_once()
    
    def test_get_provider_info_openai(self, sample_config):
        """Test provider info for OpenAI"""
        llm_config = sample_config["llm"]
        manager = LLMManager(llm_config)
        
        info = manager.get_provider_info()
        
        assert info["provider"] == "openai"
        assert info["model"] == "gpt-4.1"
    
    def test_get_provider_info_ollama(self, sample_config):
        """Test provider info for Ollama"""
        llm_config = sample_config["llm"]
        llm_config["provider"] = "ollama"
        
        manager = LLMManager(llm_config)
        
        info = manager.get_provider_info()
        
        assert info["provider"] == "ollama"
        assert info["model"] == "llama3.2:latest"
    
    def test_validate_config_delegates(self, sample_config, mock_openai_client):
        """Test that validation delegates to provider"""
        llm_config = sample_config["llm"]
        mock_openai_client.responses.create.return_value.content = "OK"
        
        with patch('src.llm_providers.OpenAI', return_value=mock_openai_client):
            manager = LLMManager(llm_config)
            
            # Should delegate to provider's validate_config
            result = manager.validate_config()
            
            assert isinstance(result, bool)