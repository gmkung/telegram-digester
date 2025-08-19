"""
Telegram client interface using Telethon
Handles message collection and sending summaries
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError


class TelegramDigestClient:
    def __init__(self, telegram_config: Dict[str, Any]):
        self.api_id = telegram_config['api_id']
        self.api_hash = telegram_config['api_hash']
        self.session_file = telegram_config['session_file']
        
        self.client = TelegramClient(
            self.session_file,
            self.api_id,
            self.api_hash
        )
        self._authenticated = False

    async def connect(self):
        """Connect to Telegram and authenticate if needed"""
        try:
            await self.client.connect()
            
            if not await self.client.is_user_authorized():
                print("User not authorized, requesting authentication")
                phone = input("Enter your phone number (with country code): ")
                await self.client.send_code_request(phone)
                code = input("Enter the verification code: ")
                
                try:
                    await self.client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    password = input("Two-factor authentication enabled. Enter your password: ")
                    await self.client.sign_in(password=password)
            
            self._authenticated = True
            me = await self.client.get_me()
            print(f"Authenticated as {me.first_name} (@{me.username})")
            
        except Exception as e:
            print(f"Failed to connect to Telegram: {e}")
            raise

    async def collect_messages(self, watchlist: Dict[str, Any], hours_back: int) -> List[Dict[str, Any]]:
        """
        Collect recent messages from all monitored chats
        Returns normalized message dictionaries
        """
        if not self._authenticated:
            await self.connect()
        
        # Calculate cutoff time for client-side filtering
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        print(f"Collecting messages from last {hours_back} hours (since {cutoff_time})")
        
        all_messages = []
        chats = watchlist.get('chats', [])
        
        for chat_config in chats:
            if not chat_config.get('enabled', True):
                continue
            
            chat_identifier = chat_config.get('chat_id') or chat_config.get('name')
            if not chat_identifier:
                print(f"Skipping chat config with no identifier: {chat_config}")
                continue
            
            try:
                messages = await self._collect_chat_messages(chat_identifier, cutoff_time)
                if messages:
                    all_messages.extend(messages)
                    print(f"Collected {len(messages)} messages from {chat_identifier}")
                else:
                    print(f"No recent messages from {chat_identifier}")
                    
            except Exception as e:
                print(f"Failed to collect messages from {chat_identifier}: {e}")
                continue
        
        # Sort all messages by timestamp
        all_messages.sort(key=lambda x: x['time'])
        print(f"Total messages collected: {len(all_messages)}")
        
        return all_messages

    async def _collect_chat_messages(self, chat_identifier: str, cutoff_time: datetime) -> List[Dict[str, Any]]:
        """Collect messages from a single chat with client-side time filtering"""
        try:
            # Get chat entity
            entity = await self.client.get_entity(chat_identifier)
            chat_name = getattr(entity, 'title', str(chat_identifier))
            
            messages = []
            message_limit = 500  # Fetch more to ensure we get recent ones
            
            async for message in self.client.iter_messages(entity, limit=message_limit):
                # Client-side time filtering - keep messages AFTER cutoff time
                if message.date >= cutoff_time:
                    if message.text:  # Only process messages with text
                        normalized_msg = await self._normalize_message(message, chat_name, entity)
                        messages.append(normalized_msg)
                else:
                    # Since messages are in reverse chronological order,
                    # we can stop once we hit old messages
                    break
            
            return messages
            
        except FloodWaitError as e:
            print(f"Rate limited for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return []
        except Exception as e:
            print(f"Error collecting from {chat_identifier}: {e}")
            return []

    async def _normalize_message(self, message, chat_name: str, entity) -> Dict[str, Any]:
        """Convert Telethon message to normalized dictionary format"""
        # Get sender name
        sender_name = "Unknown"
        if message.sender:
            if hasattr(message.sender, 'first_name'):
                sender_name = message.sender.first_name
                if hasattr(message.sender, 'last_name') and message.sender.last_name:
                    sender_name += f" {message.sender.last_name}"
            elif hasattr(message.sender, 'title'):
                sender_name = message.sender.title
            elif hasattr(message.sender, 'username'):
                sender_name = f"@{message.sender.username}"
        
        return {
            'chat': chat_name,
            'sender': sender_name,
            'time': message.date,
            'text': message.text or ""
        }

    async def send_summary(self, summary_text: str):
        """Send concise summary to Telegram Saved Messages"""
        if not self._authenticated:
            await self.connect()
        
        try:
            me = await self.client.get_me()
            await self.client.send_message(me.id, summary_text)
            print("Summary sent to Saved Messages")
            
        except Exception as e:
            print(f"Failed to send summary to Telegram: {e}")
            raise

    async def disconnect(self):
        """Disconnect from Telegram"""
        if self.client.is_connected():
            await self.client.disconnect()
            print("Disconnected from Telegram")


# Helper functions for use in main.py

async def collect_messages(watchlist: Dict[str, Any], hours_back: int, telegram_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Standalone function to collect messages"""
    client = TelegramDigestClient(telegram_config)
    try:
        await client.connect()
        return await client.collect_messages(watchlist, hours_back)
    finally:
        await client.disconnect()


async def send_summary(text: str, telegram_config: Dict[str, Any]):
    """Standalone function to send summary"""
    client = TelegramDigestClient(telegram_config)
    try:
        await client.connect()
        await client.send_summary(text)
    finally:
        await client.disconnect()