"""
Tests for message processor module
"""
import pytest
from datetime import datetime

from src.message_processor import MessageProcessor
from src.telegram_client import TelegramMessage


class TestMessageProcessor:
    """Test MessageProcessor functionality"""
    
    def test_init(self, sample_config, sample_watchlist):
        """Test processor initialization"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        assert processor.min_message_length == 10
        assert processor.exclude_emoji_only == True
        assert processor.include_mentions == True
        assert len(processor.compiled_money_patterns) > 0
        assert len(processor.compiled_date_patterns) > 0
    
    def test_check_mentions(self, sample_config, sample_watchlist):
        """Test mention detection"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        # Test @username mention
        assert processor._check_mentions("@testuser can you help?", "testuser") == True
        assert processor._check_mentions("testuser please respond", "testuser") == True
        assert processor._check_mentions("Hey there", "testuser") == False
        
        # Test generic mention patterns (should match @someone)
        assert processor._check_mentions("Hello @someone", "testuser") == True  # Contains @mention
        assert processor._check_mentions("you need to see this", None) == True
        assert processor._check_mentions("your input needed", None) == True
    
    def test_check_money(self, sample_config, sample_watchlist):
        """Test money detection"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        assert processor._check_money("Cost is $1,000.00") == True
        assert processor._check_money("Budget: 5000 USD") == True
        assert processor._check_money("Price 50k USD") == True
        assert processor._check_money("budget $500") == True
        assert processor._check_money("Hello world") == False
    
    def test_check_dates(self, sample_config, sample_watchlist):
        """Test date detection"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        assert processor._check_dates("Meeting today") == True
        assert processor._check_dates("Due tomorrow") == True
        assert processor._check_dates("Friday deadline") == True
        assert processor._check_dates("Jan 15") == True
        assert processor._check_dates("12/25/2024") == True
        assert processor._check_dates("Call at 2:30 PM") == True
        assert processor._check_dates("Hello world") == False
    
    def test_check_keywords(self, sample_config, sample_watchlist):
        """Test keyword detection"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        keywords = ["urgent", "deadline", "meeting"]
        
        assert processor._check_keywords("This is urgent", keywords) == True
        assert processor._check_keywords("URGENT matter", keywords) == True
        assert processor._check_keywords("deadline tomorrow", keywords) == True
        assert processor._check_keywords("Hello world", keywords) == False
        assert processor._check_keywords("", keywords) == False
    
    def test_filter_messages_basic(self, sample_config, sample_watchlist, sample_messages):
        """Test basic message filtering"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        filtered = processor.filter_messages(sample_messages, "testuser")
        
        # Should filter out emoji-only message and include others based on content
        assert len(filtered) >= 2  # At least the mention and budget messages
        
        # Check that mention message has high priority
        mention_msg = next((m for m in filtered if m.contains_mention), None)
        assert mention_msg is not None
        assert mention_msg.priority_score >= 10
    
    def test_filter_messages_empty(self, sample_config, sample_watchlist):
        """Test filtering with empty message list"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        filtered = processor.filter_messages([], "testuser")
        assert len(filtered) == 0
    
    def test_filter_short_messages(self, sample_config, sample_watchlist):
        """Test filtering of short messages"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        short_message = TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test",
            message_id=1,
            timestamp=datetime.now(),
            sender_id=123,
            sender_name="Test",
            text="Hi",  # Too short
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        )
        
        filtered = processor.filter_messages([short_message], "testuser")
        assert len(filtered) == 0
    
    def test_filter_emoji_only(self, sample_config, sample_watchlist):
        """Test filtering of emoji-only messages"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        emoji_message = TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test",
            message_id=1,
            timestamp=datetime.now(),
            sender_id=123,
            sender_name="Test",
            text="👍🎉😊",  # Emoji only
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        )
        
        filtered = processor.filter_messages([emoji_message], "testuser")
        assert len(filtered) == 0
    
    def test_get_chat_keywords(self, sample_config, sample_watchlist):
        """Test chat-specific keyword retrieval"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        # Test channel keywords
        keywords = processor._get_chat_keywords(123, "@test_channel")
        assert "urgent" in keywords
        assert "deadline" in keywords
        assert "meeting" in keywords
        
        # Test chat keywords
        keywords = processor._get_chat_keywords(-1001234567890, "Test Group")
        assert "project" in keywords
        assert "budget" in keywords
        
        # Test unknown chat
        keywords = processor._get_chat_keywords(999, "Unknown")
        assert len(keywords) == 0
    
    def test_format_messages_for_llm(self, sample_config, sample_watchlist, sample_filtered_messages):
        """Test formatting messages for LLM"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        formatted = processor.format_messages_for_llm(sample_filtered_messages)
        
        assert "Test Group" in formatted
        assert "Alice:" in formatted
        assert "Bob:" in formatted
        assert "Carol:" in formatted
        assert "Message Statistics:" in formatted
        assert "Total messages:" in formatted
    
    def test_format_empty_messages(self, sample_config, sample_watchlist):
        """Test formatting empty message list"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        formatted = processor.format_messages_for_llm([])
        assert formatted == "No messages to process."
    
    def test_redact_sensitive_info(self, sample_config, sample_watchlist):
        """Test sensitive information redaction"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        text = "Contact me at john@example.com or +1-555-123-4567"
        redacted = processor.redact_sensitive_info(text)
        
        assert "[EMAIL]" in redacted
        assert "[PHONE]" in redacted
        assert "john@example.com" not in redacted
        assert "+1-555-123-4567" not in redacted
    
    def test_redact_disabled(self, sample_config, sample_watchlist):
        """Test when redaction is disabled"""
        # Disable redaction in the digest config (where the processor looks)
        sample_config["digest"]["security"] = {"redact_sensitive": False}
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        text = "Contact me at john@example.com"
        redacted = processor.redact_sensitive_info(text)
        
        assert redacted == text  # Should be unchanged
    
    def test_priority_scoring(self, sample_config, sample_watchlist):
        """Test priority scoring system"""
        processor = MessageProcessor(sample_config["digest"], sample_watchlist)
        
        # Create test messages with different priority elements
        high_priority = TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test",
            message_id=1,
            timestamp=datetime.now(),
            sender_id=123,
            sender_name="Test",
            text="@testuser urgent: deadline today, budget $1000",
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        )
        
        medium_priority = TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test",
            message_id=2,
            timestamp=datetime.now(),
            sender_id=124,
            sender_name="Test2",
            text="meeting tomorrow about project budget",
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        )
        
        filtered = processor.filter_messages([high_priority, medium_priority], "testuser")
        
        # Should be sorted by priority score (highest first)
        assert len(filtered) >= 2
        assert filtered[0].priority_score >= filtered[1].priority_score
        
        # High priority message should have mention bonus
        high_pri_msg = next((m for m in filtered if m.contains_mention), None)
        assert high_pri_msg is not None
        assert high_pri_msg.priority_score >= 10  # Mention bonus