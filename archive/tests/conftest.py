"""
Test configuration and fixtures
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from datetime import datetime
import yaml

from src.telegram_client import TelegramMessage
from src.message_processor import FilteredMessage


@pytest.fixture
def sample_config():
    """Sample configuration for testing"""
    return {
        "telegram": {
            "api_id": "123456",
            "api_hash": "test_hash",
            "session_file": "./data/test_session.session"
        },
        "llm": {
            "provider": "openai",
            "openai": {
                "api_key": "test_key",
                "model": "gpt-4.1",
                "max_tokens": 2000,
                "temperature": 0.3
            },
            "ollama": {
                "base_url": "http://localhost:11434",
                "model": "llama3.2:latest",
                "temperature": 0.3,
                "top_p": 0.9
            }
        },
        "digest": {
            "interval_minutes": 240,
            "max_messages_per_chat": 100,
            "lookback_hours": 4,
            "filters": {
                "min_message_length": 10,
                "exclude_emoji_only": True,
                "include_mentions": True,
                "include_keywords": True,
                "include_money_amounts": True,
                "include_dates": True
            }
        },
        "output": {
            "send_to_saved_messages": True,
            "include_json_attachment": True,
            "format_markdown": True
        },
        "storage": {
            "data_directory": "./test_data",
            "backup_days": 30
        },
        "security": {
            "redact_sensitive": True,
            "sensitive_chat_denylist": []
        }
    }


@pytest.fixture
def sample_watchlist():
    """Sample watchlist configuration for testing"""
    return {
        "watchlist": {
            "channels": [
                {
                    "name": "@test_channel",
                    "enabled": True,
                    "keywords": ["urgent", "deadline", "meeting"],
                    "max_messages": 50,
                    "priority": "high"
                }
            ],
            "chats": [
                {
                    "name": "Test Group",
                    "chat_id": -1001234567890,
                    "enabled": True,
                    "keywords": ["project", "budget"],
                    "max_messages": 30,
                    "priority": "medium"
                }
            ]
        },
        "global_keywords": ["urgent", "deadline", "meeting", "decision"],
        "financial_keywords": ["$", "USD", "budget", "cost"],
        "temporal_keywords": ["today", "tomorrow", "deadline", "meeting"]
    }


@pytest.fixture
def sample_messages():
    """Sample Telegram messages for testing"""
    return [
        TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test Group",
            message_id=1,
            timestamp=datetime(2024, 1, 15, 10, 30),
            sender_id=123,
            sender_name="Alice",
            text="@testuser can you review the budget proposal by Friday?",
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        ),
        TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test Group", 
            message_id=2,
            timestamp=datetime(2024, 1, 15, 11, 15),
            sender_id=456,
            sender_name="Bob",
            text="Meeting moved to 2pm tomorrow",
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        ),
        TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test Group",
            message_id=3,
            timestamp=datetime(2024, 1, 15, 12, 0),
            sender_id=789,
            sender_name="Carol",
            text="Budget approved - $50,000 for Q1 project",
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        ),
        TelegramMessage(
            source="telegram",
            chat_id=-1001234567890,
            chat_name="Test Group",
            message_id=4,
            timestamp=datetime(2024, 1, 15, 12, 30),
            sender_id=101,
            sender_name="Dave",
            text="👍",  # Emoji-only message
            is_reply=False,
            reply_to_id=None,
            has_media=False,
            media_type=None
        )
    ]


@pytest.fixture
def sample_filtered_messages(sample_messages):
    """Sample filtered messages for testing"""
    return [
        FilteredMessage(
            message=sample_messages[0],
            matched_filters=["mention", "date"],
            priority_score=13,
            contains_mention=True,
            contains_money=False,
            contains_date=True,
            contains_keywords=False
        ),
        FilteredMessage(
            message=sample_messages[1],
            matched_filters=["date", "keywords"],
            priority_score=5,
            contains_mention=False,
            contains_money=False,
            contains_date=True,
            contains_keywords=True
        ),
        FilteredMessage(
            message=sample_messages[2],
            matched_filters=["money", "keywords"],
            priority_score=7,
            contains_mention=False,
            contains_money=True,
            contains_date=False,
            contains_keywords=True
        )
    ]


@pytest.fixture
def sample_digest_json():
    """Sample digest JSON response for testing"""
    return {
        "urgent": ["Budget review needed by Friday"],
        "decisions": ["Budget approved - $50,000 for Q1 project"],
        "topics": [
            {
                "topic": "Budget Planning",
                "summary": "Discussion about Q1 budget allocation and approval process",
                "participants": ["Alice", "Bob", "Carol"]
            }
        ],
        "people_updates": [
            {
                "person": "Carol",
                "update": "Approved the Q1 budget of $50,000"
            }
        ],
        "calendar": [
            {
                "event": "Budget review deadline", 
                "date": "Friday",
                "time": None
            },
            {
                "event": "Team meeting",
                "date": "tomorrow",
                "time": "14:00"
            }
        ],
        "unanswered_mentions": [
            "@testuser can you review the budget proposal by Friday?"
        ]
    }


@pytest.fixture
def temp_data_dir():
    """Temporary data directory for testing"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing"""
    client = Mock()
    response = Mock()
    response.content = '{"urgent": [], "decisions": [], "topics": [], "people_updates": [], "calendar": [], "unanswered_mentions": []}'
    client.responses.create.return_value = response
    return client


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for Ollama testing"""
    client = AsyncMock()
    response = Mock()  # Use regular Mock for response
    response.status_code = 200
    response.json.return_value = {
        "message": {
            "content": '{"urgent": [], "decisions": [], "topics": [], "people_updates": [], "calendar": [], "unanswered_mentions": []}'
        },
        "eval_duration": 1000000000,  # 1 second in nanoseconds
        "eval_count": 50
    }
    response.raise_for_status.return_value = None
    client.post.return_value = response
    return client


@pytest.fixture
def mock_telethon_client():
    """Mock Telethon client for testing"""
    client = AsyncMock()
    client.connect.return_value = None
    client.is_user_authorized.return_value = True
    client.get_me.return_value = Mock(first_name="Test", username="testuser", id=123456)
    client.get_entity.return_value = Mock(id=-1001234567890, title="Test Group")
    client.send_message.return_value = None
    client.disconnect.return_value = None
    return client