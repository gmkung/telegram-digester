"""
Simple message processing
"""
import logging
from typing import List
from dataclasses import dataclass
from src.telegram_client import TelegramMessage


logger = logging.getLogger(__name__)


@dataclass
class FilteredMessage:
    """Simple message wrapper"""
    message: TelegramMessage


class MessageProcessor:
    """Simple message processor - no filtering"""
    
    def __init__(self, config=None, watchlist=None):
        pass
    
    def filter_messages(self, messages: List[TelegramMessage], username: str = None) -> List[FilteredMessage]:
        """Return all messages without filtering"""
        filtered_messages = [FilteredMessage(message=msg) for msg in messages]
        logger.info(f"Processed {len(filtered_messages)} messages (no filtering)")
        return filtered_messages
    
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