"""
Integration tests for the complete digest pipeline
"""
import pytest
import tempfile
import json
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from src.telegram_client import TelegramDigestClient, TelegramMessage
from src.message_processor import MessageProcessor
from src.digest_generator import DigestGenerator
from src.storage import StorageManager
from src.llm_providers import LLMManager


@pytest.mark.integration
class TestDigestPipeline:
    """Integration tests for the complete digest pipeline"""
    
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, sample_config, sample_watchlist, sample_messages, sample_digest_json):
        """Test the complete digest generation pipeline"""
        
        # Mock LLM response
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_digest.return_value = sample_digest_json
        mock_llm_manager.get_provider_info.return_value = {"provider": "openai", "model": "gpt-4.1"}
        mock_llm_manager.validate_config.return_value = True
        
        # Initialize components
        with tempfile.TemporaryDirectory() as temp_dir:
            # Update config for temp directory
            sample_config["storage"]["data_directory"] = temp_dir
            
            # Initialize storage
            storage = StorageManager(sample_config)
            
            # Initialize message processor
            processor = MessageProcessor(sample_config["digest"], sample_watchlist)
            
            # Initialize digest generator with mocked LLM
            generator = DigestGenerator(sample_config)
            generator.llm_manager = mock_llm_manager
            
            # Test the pipeline
            # 1. Filter messages
            filtered_messages = processor.filter_messages(sample_messages, "testuser")
            assert len(filtered_messages) > 0
            
            # 2. Generate digest
            system_prompt = "Test system prompt for {username}"
            digest_result = await generator.generate_digest(
                filtered_messages, 
                system_prompt, 
                "testuser"
            )
            
            assert digest_result.success == True
            assert digest_result.structured_data["urgent"] == sample_digest_json["urgent"]
            
            # 3. Save to storage
            digest_data = {
                "digest": digest_result.structured_data,
                "metadata": digest_result.metadata,
                "generated_at": "2024-01-15T10:30:00"
            }
            
            success = storage.save_last_digest(digest_data)
            assert success == True
            
            # 4. Export JSON
            json_path = storage.export_digest_json(digest_data)
            assert Path(json_path).exists()
            
            # Verify final output
            with open(json_path, 'r') as f:
                exported_data = json.load(f)
            assert exported_data["digest"]["urgent"] == sample_digest_json["urgent"]
    
    @pytest.mark.asyncio 
    async def test_pipeline_with_empty_messages(self, sample_config, sample_watchlist, sample_digest_json):
        """Test pipeline behavior with no messages"""
        
        # Mock LLM (shouldn't be called with empty messages)
        mock_llm_manager = AsyncMock()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_config["storage"]["data_directory"] = temp_dir
            
            # Initialize components
            processor = MessageProcessor(sample_config["digest"], sample_watchlist)
            generator = DigestGenerator(sample_config)
            generator.llm_manager = mock_llm_manager
            
            # Test with empty message list
            filtered_messages = processor.filter_messages([], "testuser")
            assert len(filtered_messages) == 0
            
            # Generate digest should handle empty messages gracefully
            digest_result = await generator.generate_digest(
                filtered_messages,
                "Test prompt",
                "testuser"
            )
            
            assert digest_result.success == True
            assert digest_result.digest_text == "No new messages to digest."
            assert digest_result.metadata["message_count"] == 0
            
            # LLM should not have been called
            mock_llm_manager.generate_digest.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_pipeline_with_llm_failure(self, sample_config, sample_watchlist, sample_messages):
        """Test pipeline behavior when LLM fails"""
        
        # Mock LLM to fail
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_digest.side_effect = Exception("LLM connection failed")
        mock_llm_manager.get_provider_info.return_value = {"provider": "openai", "model": "gpt-4.1"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_config["storage"]["data_directory"] = temp_dir
            
            # Initialize components
            processor = MessageProcessor(sample_config["digest"], sample_watchlist)
            generator = DigestGenerator(sample_config)
            generator.llm_manager = mock_llm_manager
            storage = StorageManager(sample_config)
            
            # Process messages
            filtered_messages = processor.filter_messages(sample_messages, "testuser")
            assert len(filtered_messages) > 0
            
            # Generate digest should fail gracefully
            digest_result = await generator.generate_digest(
                filtered_messages,
                "Test prompt", 
                "testuser"
            )
            
            assert digest_result.success == False
            assert "LLM connection failed" in digest_result.error_message
            assert digest_result.digest_text == "Failed to generate digest due to error."
            
            # Should still be able to save error state
            from src.storage import DigestRun
            error_run = DigestRun(
                timestamp="2024-01-15T10:30:00",
                message_count=len(filtered_messages),
                chat_count=1,
                success=False,
                error_message=digest_result.error_message
            )
            
            success = storage.save_digest_run(error_run)
            assert success == True
    
    @pytest.mark.asyncio
    async def test_pipeline_with_invalid_json_response(self, sample_config, sample_watchlist, sample_messages):
        """Test pipeline behavior with invalid LLM JSON response"""
        
        # Mock LLM to return invalid JSON
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_digest.return_value = {
            "urgent": ["Test urgent item"],
            "decisions": [],
            "topics": "invalid_structure",  # Should be array
            "people_updates": [],
            "calendar": [],
            "unanswered_mentions": [],
            "_error": "JSON parsing failed"
        }
        mock_llm_manager.get_provider_info.return_value = {"provider": "openai", "model": "gpt-4.1"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_config["storage"]["data_directory"] = temp_dir
            
            # Initialize components
            processor = MessageProcessor(sample_config["digest"], sample_watchlist)
            generator = DigestGenerator(sample_config)
            generator.llm_manager = mock_llm_manager
            
            # Process messages
            filtered_messages = processor.filter_messages(sample_messages, "testuser")
            
            # Generate digest
            digest_result = await generator.generate_digest(
                filtered_messages,
                "Test prompt",
                "testuser"
            )
            
            # Should succeed but with validation errors
            assert digest_result.success == True
            assert digest_result.structured_data["urgent"] == ["Test urgent item"]
            assert digest_result.metadata["validation_errors"]  # Should have validation errors
    
    @pytest.mark.asyncio
    async def test_cursor_persistence_across_runs(self, sample_config, sample_watchlist, sample_messages):
        """Test that cursors persist across multiple digest runs"""
        
        mock_llm_manager = AsyncMock()
        mock_llm_manager.generate_digest.return_value = {
            "urgent": [], "decisions": [], "topics": [], 
            "people_updates": [], "calendar": [], "unanswered_mentions": []
        }
        mock_llm_manager.get_provider_info.return_value = {"provider": "openai", "model": "gpt-4.1"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_config["storage"]["data_directory"] = temp_dir
            
            # First run
            storage1 = StorageManager(sample_config)
            
            # Load initial cursors (should be empty)
            cursors1 = storage1.load_cursors()
            assert len(cursors1) == 0
            
            # Simulate message processing with cursors
            updated_cursors = {
                "@test_channel": 12345,
                "-1001234567890": 67890
            }
            
            success = storage1.save_cursors(updated_cursors)
            assert success == True
            
            # Second run with new storage instance (simulating restart)
            storage2 = StorageManager(sample_config)
            cursors2 = storage2.load_cursors()
            
            # Cursors should persist
            assert cursors2["@test_channel"] == 12345
            assert cursors2["-1001234567890"] == 67890
    
    @pytest.mark.asyncio
    async def test_message_filtering_priority_ordering(self, sample_config, sample_watchlist):
        """Test that message filtering properly prioritizes messages"""
        
        from datetime import datetime
        
        # Create messages with different priority levels
        messages = [
            # Low priority - just keywords
            TelegramMessage(
                source="telegram", chat_id=-1001234567890, chat_name="Test",
                message_id=1, timestamp=datetime.now(), sender_id=1, sender_name="User1",
                text="Let's have a meeting next week about the project",
                is_reply=False, reply_to_id=None, has_media=False, media_type=None
            ),
            # High priority - mention + money + deadline
            TelegramMessage(
                source="telegram", chat_id=-1001234567890, chat_name="Test", 
                message_id=2, timestamp=datetime.now(), sender_id=2, sender_name="User2",
                text="@testuser urgent: need approval for $50,000 budget by Friday deadline",
                is_reply=False, reply_to_id=None, has_media=False, media_type=None
            ),
            # Medium priority - money + date
            TelegramMessage(
                source="telegram", chat_id=-1001234567890, chat_name="Test",
                message_id=3, timestamp=datetime.now(), sender_id=3, sender_name="User3", 
                text="Budget proposal costs $25,000 due tomorrow",
                is_reply=False, reply_to_id=None, has_media=False, media_type=None
            )
        ]
        
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        filtered_messages = processor.filter_messages(messages, "testuser")
        
        # Should be sorted by priority (highest first)
        assert len(filtered_messages) >= 2
        assert filtered_messages[0].priority_score >= filtered_messages[1].priority_score
        
        # Highest priority should be the mention with money and deadline
        highest_priority = filtered_messages[0]
        assert highest_priority.contains_mention == True
        assert highest_priority.contains_money == True
        assert highest_priority.contains_date == True
        assert highest_priority.priority_score >= 15  # 10 (mention) + 5 (money) + 3 (date) + bonuses