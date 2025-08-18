"""
Tests for digest generator module
"""
import pytest
import json
import tempfile
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from src.digest_generator import DigestGenerator
from src.llm_providers import LLMManager


class TestDigestGenerator:
    """Test DigestGenerator functionality"""
    
    def test_init(self, sample_config):
        """Test digest generator initialization"""
        generator = DigestGenerator(sample_config)
        
        assert generator.config == sample_config
        assert isinstance(generator.llm_manager, LLMManager)
        assert "urgent" in generator.digest_schema["properties"]
        assert "decisions" in generator.digest_schema["properties"]
    
    @pytest.mark.asyncio
    async def test_generate_digest_success(self, sample_config, sample_filtered_messages, sample_digest_json):
        """Test successful digest generation"""
        generator = DigestGenerator(sample_config)
        
        # Mock LLM manager
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_digest.return_value = sample_digest_json
        mock_llm_manager.get_provider_info.return_value = {"provider": "openai", "model": "gpt-4.1"}
        generator.llm_manager = mock_llm_manager
        
        result = await generator.generate_digest(
            sample_filtered_messages, 
            "Test system prompt", 
            "testuser"
        )
        
        assert result.success == True
        assert result.structured_data["urgent"] == sample_digest_json["urgent"]
        assert result.structured_data["decisions"] == sample_digest_json["decisions"]
        assert "📊 **Message Digest**" in result.digest_text
        assert result.metadata["message_count"] == len(sample_filtered_messages)
    
    @pytest.mark.asyncio
    async def test_generate_digest_empty_messages(self, sample_config):
        """Test digest generation with empty message list"""
        generator = DigestGenerator(sample_config)
        
        result = await generator.generate_digest([], "Test system prompt", "testuser")
        
        assert result.success == True
        assert result.digest_text == "No new messages to digest."
        assert result.structured_data["urgent"] == []
        assert result.metadata["message_count"] == 0
    
    @pytest.mark.asyncio
    async def test_generate_digest_llm_error(self, sample_config, sample_filtered_messages):
        """Test digest generation with LLM error"""
        generator = DigestGenerator(sample_config)
        
        # Mock LLM manager to raise error
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_digest.side_effect = Exception("LLM API Error")
        generator.llm_manager = mock_llm_manager
        
        result = await generator.generate_digest(
            sample_filtered_messages, 
            "Test system prompt", 
            "testuser"
        )
        
        assert result.success == False
        assert "LLM API Error" in result.error_message
        assert result.digest_text == "Failed to generate digest due to error."
    
    def test_validate_digest_schema_valid(self, sample_config, sample_digest_json):
        """Test schema validation with valid data"""
        generator = DigestGenerator(sample_config)
        
        result = generator._validate_digest_schema(sample_digest_json)
        
        assert result["valid"] == True
        assert len(result["errors"]) == 0
    
    def test_validate_digest_schema_missing_fields(self, sample_config):
        """Test schema validation with missing fields"""
        generator = DigestGenerator(sample_config)
        
        invalid_data = {"urgent": [], "decisions": []}  # Missing required fields
        
        result = generator._validate_digest_schema(invalid_data)
        
        assert result["valid"] == False
        assert len(result["errors"]) > 0
        assert "Missing required fields" in result["errors"][0]
    
    def test_validate_digest_schema_wrong_types(self, sample_config):
        """Test schema validation with wrong data types"""
        generator = DigestGenerator(sample_config)
        
        invalid_data = {
            "urgent": "not an array",  # Should be array
            "decisions": [],
            "topics": [],
            "people_updates": [],
            "calendar": [],
            "unanswered_mentions": []
        }
        
        result = generator._validate_digest_schema(invalid_data)
        
        assert result["valid"] == False
        assert any("must be an array" in error for error in result["errors"])
    
    def test_validate_digest_schema_invalid_topics(self, sample_config):
        """Test schema validation with invalid topic structure"""
        generator = DigestGenerator(sample_config)
        
        invalid_data = {
            "urgent": [],
            "decisions": [],
            "topics": [{"invalid": "structure"}],  # Missing required fields
            "people_updates": [],
            "calendar": [],
            "unanswered_mentions": []
        }
        
        result = generator._validate_digest_schema(invalid_data)
        
        assert result["valid"] == False
        assert any("missing required fields" in error for error in result["errors"])
    
    def test_fix_digest_schema(self, sample_config):
        """Test automatic schema fixing"""
        generator = DigestGenerator(sample_config)
        
        broken_data = {
            "urgent": "not an array",
            "decisions": None,
            "topics": [{"topic": "Test", "summary": "Summary", "participants": "not_array"}],
            "people_updates": [{"person": "John"}],  # Missing update field
            "calendar": [{"event": "Meeting"}],  # Missing date field
            "unanswered_mentions": []
        }
        
        fixed_data = generator._fix_digest_schema(broken_data)
        
        assert isinstance(fixed_data["urgent"], list)
        assert isinstance(fixed_data["decisions"], list)
        assert isinstance(fixed_data["topics"], list)
        assert len(fixed_data["topics"]) == 1  # Valid topic should remain
        assert len(fixed_data["people_updates"]) == 0  # Invalid update removed
        assert len(fixed_data["calendar"]) == 0  # Invalid event removed
    
    def test_format_digest_text_full(self, sample_config, sample_digest_json):
        """Test digest text formatting with all sections"""
        generator = DigestGenerator(sample_config)
        
        text = generator._format_digest_text(sample_digest_json)
        
        assert "🚨 **URGENT ITEMS**" in text
        assert "✅ **DECISIONS MADE**" in text
        assert "💡 **KEY TOPICS DISCUSSED**" in text
        assert "👥 **PEOPLE UPDATES**" in text
        assert "📅 **CALENDAR & DEADLINES**" in text
        assert "💬 **REQUIRES YOUR RESPONSE**" in text
        assert "📊 **Message Digest**" in text
    
    def test_format_digest_text_empty(self, sample_config):
        """Test digest text formatting with empty data"""
        generator = DigestGenerator(sample_config)
        
        empty_data = {
            "urgent": [],
            "decisions": [],
            "topics": [],
            "people_updates": [],
            "calendar": [],
            "unanswered_mentions": []
        }
        
        text = generator._format_digest_text(empty_data)
        
        assert text == "No significant updates in recent messages."
    
    def test_format_digest_text_partial(self, sample_config):
        """Test digest text formatting with partial data"""
        generator = DigestGenerator(sample_config)
        
        partial_data = {
            "urgent": ["Important matter"],
            "decisions": [],
            "topics": [],
            "people_updates": [],
            "calendar": [],
            "unanswered_mentions": ["@user respond please"]
        }
        
        text = generator._format_digest_text(partial_data)
        
        assert "🚨 **URGENT ITEMS**" in text
        assert "💬 **REQUIRES YOUR RESPONSE**" in text
        assert "✅ **DECISIONS MADE**" not in text  # Empty section should not appear
    
    @pytest.mark.asyncio
    async def test_save_digest_json(self, sample_config):
        """Test saving digest as JSON file"""
        generator = DigestGenerator(sample_config)
        
        # Create a mock digest result
        from src.digest_generator import DigestResult
        digest_result = DigestResult(
            success=True,
            digest_text="Test digest",
            structured_data={"urgent": [], "decisions": []},
            metadata={"test": "data"}
        )
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            success = await generator.save_digest_json(digest_result, tmp_path)
            assert success == True
            
            # Verify file contents
            with open(tmp_path, 'r') as f:
                saved_data = json.load(f)
            
            assert saved_data["success"] == True
            assert saved_data["digest"] == digest_result.structured_data
            assert saved_data["metadata"] == digest_result.metadata
            
        finally:
            Path(tmp_path).unlink()  # Clean up
    
    @pytest.mark.asyncio
    async def test_save_digest_json_error(self, sample_config):
        """Test saving digest JSON with error"""
        generator = DigestGenerator(sample_config)
        
        from src.digest_generator import DigestResult
        digest_result = DigestResult(
            success=False,
            digest_text="Error occurred",
            structured_data={},
            error_message="Test error"
        )
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            success = await generator.save_digest_json(digest_result, tmp_path)
            assert success == True
            
            # Verify error is saved
            with open(tmp_path, 'r') as f:
                saved_data = json.load(f)
            
            assert saved_data["success"] == False
            assert saved_data["error"] == "Test error"
            
        finally:
            Path(tmp_path).unlink()  # Clean up
    
    @pytest.mark.asyncio
    async def test_save_digest_json_file_error(self, sample_config):
        """Test saving digest JSON with file system error"""
        generator = DigestGenerator(sample_config)
        
        from src.digest_generator import DigestResult
        digest_result = DigestResult(
            success=True,
            digest_text="Test",
            structured_data={}
        )
        
        # Try to save to an invalid path
        success = await generator.save_digest_json(digest_result, "/invalid/path/file.json")
        assert success == False