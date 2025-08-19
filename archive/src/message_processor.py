"""
Message processing with time-based filtering
"""
import logging
from datetime import datetime, timedelta
from typing import List
from dataclasses import dataclass
from src.telegram_client import TelegramMessage


logger = logging.getLogger(__name__)


@dataclass
class FilteredMessage:
    """Message wrapper with filtering metadata"""
    message: TelegramMessage
    priority_score: float = 0.0
    filter_reason: str = ""


class MessageProcessor:
    """Message processor with time-based filtering"""
    
    def __init__(self, config=None, watchlist=None):
        self.config = config or {}
        self.watchlist = watchlist or {}
        
        # Get filtering settings from config
        digest_config = self.config.get('digest', {})
        self.lookback_hours = digest_config.get('lookback_hours', 72)  # Default to 3 days
        self.max_messages_per_chat = digest_config.get('max_messages_per_chat', 100)
        
        # Get filter options
        filters = digest_config.get('filters', {})
        self.min_message_length = filters.get('min_message_length', 10)
        self.exclude_emoji_only = filters.get('exclude_emoji_only', True)
        self.include_mentions = filters.get('include_mentions', True)
        self.include_keywords = filters.get('include_keywords', True)
        self.include_money_amounts = filters.get('include_money_amounts', True)
        self.include_dates = filters.get('include_dates', True)
    
    def filter_messages(self, messages: List[TelegramMessage], username: str = None) -> List[FilteredMessage]:
        """Filter messages based on time and relevance"""
        if not messages:
            return []
        
        # Time filtering is now done server-side, so we only do relevance filtering
        filtered_messages = []
        total_messages = len(messages)
        relevance_filtered = 0
        
        for msg in messages:
            
            # Create filtered message
            filtered_msg = FilteredMessage(message=msg)
            
            # Calculate priority score
            priority_score = self._calculate_priority_score(msg, username)
            filtered_msg.priority_score = priority_score
            
            # Apply relevance filters
            if self._is_message_relevant(msg):
                filtered_messages.append(filtered_msg)
            else:
                relevance_filtered += 1
        
        # Sort by priority (highest first)
        filtered_messages.sort(key=lambda x: x.priority_score, reverse=True)
        
        # Apply per-chat message limits
        final_messages = self._apply_chat_limits(filtered_messages)
        
        logger.info(f"Filtered {total_messages} messages: {len(final_messages)} kept, {relevance_filtered} irrelevant (time filtering done server-side)")
        return final_messages
    
    def format_messages_for_llm(self, filtered_messages: List[FilteredMessage]) -> str:
        """Format messages for LLM processing"""
        if not filtered_messages:
            return "No messages to process."
        
        # Group messages by chat
        messages_by_chat = {}
        for filtered_msg in filtered_messages:
            chat_name = filtered_msg.message.chat_name
            if chat_name not in messages_by_chat:
                messages_by_chat[chat_name] = []
            messages_by_chat[chat_name].append(filtered_msg)
        
        # Format output
        formatted_text = ""
        
        for chat_name, chat_messages in messages_by_chat.items():
            formatted_text += f"\n## {chat_name} ({len(chat_messages)} messages)\n"
            
            # Sort messages by timestamp within each chat
            chat_messages.sort(key=lambda x: x.message.timestamp)
            
            # Add time range info
            if chat_messages:
                start_time = chat_messages[0].message.timestamp.strftime("%H:%M")
                end_time = chat_messages[-1].message.timestamp.strftime("%H:%M")
                date = chat_messages[0].message.timestamp.strftime("%Y-%m-%d")
                formatted_text += f"Time range: {date} {start_time} - {end_time}\n\n"
            
            # Add messages
            for filtered_msg in chat_messages:
                msg = filtered_msg.message
                timestamp = msg.timestamp.strftime("%H:%M")
                formatted_text += f"[{timestamp}] {msg.sender_name}: {msg.text}\n"
                
                # Add media info if present
                if msg.has_media:
                    formatted_text += f"    [Media: {msg.media_type}]\n"
                
                # Add reply context if it's a reply
                if msg.is_reply:
                    formatted_text += f"    [Reply to message {msg.reply_to_id}]\n"
            
            formatted_text += "\n"
        
        # Add summary statistics
        total_messages = len(filtered_messages)
        stats = f"""
Message Statistics:
- Total messages: {total_messages}
- Chats involved: {len(messages_by_chat)}
"""
        
        return stats + "\nMessages:\n" + formatted_text
    
    def _calculate_priority_score(self, msg: TelegramMessage, username: str = None) -> float:
        """Calculate priority score for a message"""
        score = 0.0
        
        # Base score for recent messages - always use UTC for consistency
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        hours_ago = (now - msg.timestamp).total_seconds() / 3600
        if hours_ago < 1:
            score += 10.0  # Very recent
        elif hours_ago < 6:
            score += 8.0   # Recent
        elif hours_ago < 24:
            score += 6.0   # Today
        elif hours_ago < 48:
            score += 4.0   # Yesterday
        else:
            score += 2.0   # Older
        
        # Boost for mentions
        if username and username.lower() in msg.text.lower():
            score += 5.0
        
        # Boost for replies (indicates conversation)
        if msg.is_reply:
            score += 2.0
        
        # Boost for media (often more important)
        if msg.has_media:
            score += 1.0
        
        # Boost for longer messages (more content)
        if len(msg.text) > 50:
            score += 1.0
        
        return score
    
    def _is_message_relevant(self, msg: TelegramMessage) -> bool:
        """Check if message meets relevance criteria"""
        # Skip very short messages
        if len(msg.text.strip()) < self.min_message_length:
            return False
        
        # Skip emoji-only messages if configured
        if self.exclude_emoji_only and self._is_emoji_only(msg.text):
            return False
        
        # Include messages with mentions
        if self.include_mentions and '@' in msg.text:
            return True
        
        # Include messages with keywords
        if self.include_keywords and self._has_keywords(msg.text):
            return True
        
        # Include messages with money amounts
        if self.include_money_amounts and self._has_money_amounts(msg.text):
            return True
        
        # Include messages with dates
        if self.include_dates and self._has_dates(msg.text):
            return True
        
        # Include messages with media
        if msg.has_media:
            return True
        
        # Include replies (conversation context)
        if msg.is_reply:
            return True
        
        # Default: include if it's a reasonable length
        return len(msg.text.strip()) >= 20
    
    def _is_emoji_only(self, text: str) -> bool:
        """Check if text is mostly emojis"""
        import re
        # Remove common punctuation and whitespace
        clean_text = re.sub(r'[^\w\s]', '', text).strip()
        return len(clean_text) < len(text) * 0.3
    
    def _has_keywords(self, text: str) -> bool:
        """Check if text contains relevant keywords"""
        keywords = ['urgent', 'important', 'update', 'announcement', 'deadline', 'meeting', 'call', 'event']
        return any(keyword.lower() in text.lower() for keyword in keywords)
    
    def _has_money_amounts(self, text: str) -> bool:
        """Check if text contains money amounts"""
        import re
        money_patterns = [
            r'\$\d+',           # $100
            r'\d+\s*USD',       # 100 USD
            r'\d+\s*ETH',       # 100 ETH
            r'\d+\s*PNK',       # 100 PNK
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in money_patterns)
    
    def _has_dates(self, text: str) -> bool:
        """Check if text contains dates"""
        import re
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
            r'today|tomorrow|yesterday',
            r'next week|last week',
        ]
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in date_patterns)
    
    def _apply_chat_limits(self, messages: List[FilteredMessage]) -> List[FilteredMessage]:
        """Apply per-chat message limits"""
        chat_counts = {}
        final_messages = []
        
        for msg in messages:
            chat_name = msg.message.chat_name
            if chat_name not in chat_counts:
                chat_counts[chat_name] = 0
            
            if chat_counts[chat_name] < self.max_messages_per_chat:
                final_messages.append(msg)
                chat_counts[chat_name] += 1
        
        return final_messages