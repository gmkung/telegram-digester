#!/usr/bin/env python3
"""
Unit test to verify access to KlerosCurate channel
"""
import asyncio
import logging
from src.telegram_client import TelegramDigestClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_kleros_access():
    """Test if we can access KlerosCurate channel"""
    
    # Telegram config
    config = {
        'api_id': 27231177,
        'api_hash': '35b02a656fc52eaa00a7c16e47ec5450',
        'session_file': './data/user_session.session'
    }
    
    client = TelegramDigestClient(config)
    
    try:
        # Connect
        await client.connect()
        print("✅ Connected to Telegram")
        
        # Test different ways to access the channel
        test_channels = [
            "@KlerosCurate", 
            "KlerosCurate", 
            "kleros", 
            "@kleros"
        ]
        
        for channel_name in test_channels:
            print(f"\n🔍 Testing access to: {channel_name}")
            try:
                # Get entity info
                entity = await client.client.get_entity(channel_name)
                print(f"   ✅ Entity found: {entity.title} (ID: {entity.id})")
                print(f"   📊 Type: {type(entity).__name__}")
                
                # Try to get recent messages
                messages = []
                count = 0
                async for message in client.client.iter_messages(entity, limit=5):
                    if message.text:
                        count += 1
                        print(f"   📝 Message {count}: {message.text[:100]}...")
                        if count >= 3:  # Just show first 3
                            break
                
                if count == 0:
                    print(f"   ⚠️  No text messages found in recent messages")
                else:
                    print(f"   ✅ Found {count} messages")
                    
            except Exception as e:
                print(f"   ❌ Error accessing {channel_name}: {e}")
        
        # Test our bot's message collection method
        print(f"\n🤖 Testing bot's message collection method...")
        try:
            messages = await client.get_chat_messages("@KlerosCurate", limit=10)
            print(f"   ✅ Bot method retrieved {len(messages)} messages")
            for i, msg in enumerate(messages[:3]):
                print(f"   📝 Message {i+1} ({msg.timestamp}): {msg.text[:100]}...")
        except Exception as e:
            print(f"   ❌ Bot method failed: {e}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        await client.disconnect()
        print("🔌 Disconnected")

if __name__ == "__main__":
    asyncio.run(test_kleros_access())