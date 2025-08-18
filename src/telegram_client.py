"""
Telegram client implementation using Telethon
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from telethon import TelegramClient, events
from telethon.tl.types import Message, User, Chat, Channel
from telethon.errors import SessionPasswordNeededError, FloodWaitError
import yaml


logger = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    """Normalized message structure"""
    source: str
    chat_id: int
    chat_name: str
    message_id: int
    timestamp: datetime
    sender_id: Optional[int]
    sender_name: str
    text: str
    is_reply: bool
    reply_to_id: Optional[int]
    has_media: bool
    media_type: Optional[str]


class TelegramDigestClient:
    """Telegram client for message ingestion and digest delivery"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_id = config['api_id']
        self.api_hash = config['api_hash']
        self.session_file = config['session_file']
        
        self.client = TelegramClient(
            self.session_file,
            self.api_id,
            self.api_hash
        )
        self.watchlist = None
        self._authenticated = False
    
    async def connect(self):
        """Connect to Telegram and authenticate"""
        try:
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                logger.info("User not authorized, requesting authentication")
                phone = input("Please enter your phone number (with country code): ")
                await self.client.send_code_request(phone)
                code = input("Please enter the code you received: ")
                
                try:
                    await self.client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    password = input("Two-factor authentication enabled. Please enter your password: ")
                    await self.client.sign_in(password=password)
            
            self._authenticated = True
            me = await self.client.get_me()
            logger.info(f"Successfully authenticated as {me.first_name} (@{me.username})")
            
        except Exception as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            raise
    
    def load_watchlist(self, watchlist_path: str):
        """Load watchlist configuration"""
        try:
            with open(watchlist_path, 'r') as f:
                self.watchlist = yaml.safe_load(f)
            channels = self.watchlist.get('watchlist', {}).get('channels', []) or []
            chats = self.watchlist.get('watchlist', {}).get('chats', []) or []
            logger.info(f"Loaded watchlist with {len(channels)} channels and {len(chats)} chats")
        except Exception as e:
            logger.error(f"Failed to load watchlist: {e}")
            raise
    
    async def get_chat_messages(
        self, 
        chat_identifier: str, 
        limit: int = 100
    ) -> List[TelegramMessage]:
        """Fetch recent messages from a specific chat or channel"""
        try:
            # Get the chat entity
            entity = await self.client.get_entity(chat_identifier)
            
            # Get recent messages
            messages = []
            async for message in self.client.iter_messages(entity, limit=limit):
                if message.text:  # Only get messages with text
                    messages.append(await self._convert_message(message, entity))
            
            # Sort by timestamp (oldest first)
            messages.sort(key=lambda x: x.timestamp)
            
            logger.info(f"Retrieved {len(messages)} messages from {chat_identifier}")
            return messages
            
        except FloodWaitError as e:
            logger.warning(f"Rate limited for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return []
        except Exception as e:
            logger.error(f"Error fetching messages from {chat_identifier}: {e}")
            return []
    
    async def _convert_message(self, message: Message, entity) -> TelegramMessage:
        """Convert Telethon message to normalized format"""
        # Get sender information
        sender_name = "Unknown"
        sender_id = None
        
        if message.sender:
            sender_id = message.sender.id
            if hasattr(message.sender, 'first_name'):
                sender_name = message.sender.first_name
                if hasattr(message.sender, 'last_name') and message.sender.last_name:
                    sender_name += f" {message.sender.last_name}"
            elif hasattr(message.sender, 'title'):
                sender_name = message.sender.title
            elif hasattr(message.sender, 'username'):
                sender_name = f"@{message.sender.username}"
        
        # Get chat information
        chat_name = "Unknown"
        if hasattr(entity, 'title'):
            chat_name = entity.title
        elif hasattr(entity, 'first_name'):
            chat_name = entity.first_name
            if hasattr(entity, 'last_name') and entity.last_name:
                chat_name += f" {entity.last_name}"
        elif hasattr(entity, 'username'):
            chat_name = f"@{entity.username}"
        
        # Check for media
        has_media = message.media is not None
        media_type = None
        if has_media:
            if message.photo:
                media_type = "photo"
            elif message.video:
                media_type = "video"
            elif message.audio:
                media_type = "audio"
            elif message.voice:
                media_type = "voice"
            elif message.document:
                media_type = "document"
            else:
                media_type = "other"
        
        return TelegramMessage(
            source="telegram",
            chat_id=entity.id,
            chat_name=chat_name,
            message_id=message.id,
            timestamp=message.date,
            sender_id=sender_id,
            sender_name=sender_name,
            text=message.text or "",
            is_reply=message.reply_to_msg_id is not None,
            reply_to_id=message.reply_to_msg_id,
            has_media=has_media,
            media_type=media_type
        )
    
    async def collect_messages_from_watchlist(
        self, 
        max_messages_per_chat: int = 100
    ) -> List[TelegramMessage]:
        """Collect messages from all watched chats and channels"""
        all_messages = []
        
        if not self.watchlist:
            logger.warning("No watchlist loaded")
            return all_messages
        
        watchlist_config = self.watchlist.get('watchlist', {})
        
        # Process channels
        for channel_config in watchlist_config.get('channels', []):
            if not channel_config.get('enabled', True):
                continue
            
            channel_name = channel_config['name']
            max_msgs = channel_config.get('max_messages', max_messages_per_chat)
            
            try:
                messages = await self.get_chat_messages(channel_name, limit=max_msgs)
                if messages:
                    all_messages.extend(messages)
                    
            except Exception as e:
                logger.error(f"Failed to collect messages from channel {channel_name}: {e}")
        
        # Process private chats
        chats_list = watchlist_config.get('chats', []) or []
        for chat_config in chats_list:
            if not chat_config.get('enabled', True):
                continue
            
            chat_identifier = chat_config.get('chat_id') or chat_config.get('name')
            if not chat_identifier:
                logger.warning(f"No chat identifier found for chat config: {chat_config}")
                continue
            
            max_msgs = chat_config.get('max_messages', max_messages_per_chat)
            
            try:
                messages = await self.get_chat_messages(chat_identifier, limit=max_msgs)
                if messages:
                    all_messages.extend(messages)
                    
            except Exception as e:
                logger.error(f"Failed to collect messages from chat {chat_identifier}: {e}")
        
        # Sort all messages by timestamp
        all_messages.sort(key=lambda x: x.timestamp)
        
        logger.info(f"Collected {len(all_messages)} total messages")
        return all_messages
    
    async def send_to_saved_messages(self, text: str, file_path: Optional[str] = None):
        """Send digest to Saved Messages"""
        try:
            me = await self.client.get_me()
            
            if file_path:
                await self.client.send_file(
                    me.id,
                    file_path,
                    caption=text
                )
            else:
                await self.client.send_message(me.id, text)
            
            logger.info("Successfully sent digest to Saved Messages")
            
        except Exception as e:
            logger.error(f"Failed to send digest to Saved Messages: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Telegram"""
        if self.client.is_connected():
            await self.client.disconnect()
            logger.info("Disconnected from Telegram")