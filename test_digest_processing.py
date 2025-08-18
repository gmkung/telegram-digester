#!/usr/bin/env python3
"""
Test digest processing with actual KlerosCurate messages
"""
import asyncio
import logging
from src.telegram_client import TelegramDigestClient
from src.message_processor import MessageProcessor
from src.digest_generator import DigestGenerator
import yaml

logging.basicConfig(level=logging.INFO)

async def test_digest_processing():
    """Test full digest processing with real messages"""
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    with open('watchlist.yml', 'r') as f:
        watchlist = yaml.safe_load(f)
    
    # Initialize components
    telegram_client = TelegramDigestClient(config['telegram'])
    processor = MessageProcessor(config['digest'], watchlist)
    digest_generator = DigestGenerator(config)
    
    try:
        # Connect to Telegram
        await telegram_client.connect()
        print("✅ Connected to Telegram")
        
        # Get messages from KlerosCurate
        print("📥 Fetching messages from @KlerosCurate...")
        messages = await telegram_client.get_chat_messages("@KlerosCurate", limit=20)
        print(f"📊 Retrieved {len(messages)} messages")
        
        # Show sample messages
        for i, msg in enumerate(messages[:3]):
            print(f"   Message {i+1}: {msg.text[:100]}...")
        
        # Filter messages
        print("\n🔍 Filtering messages...")
        filtered_messages = processor.filter_messages(messages, "daisugist")
        print(f"📊 Filtered to {len(filtered_messages)} relevant messages")
        
        # Show filtered messages
        for i, fmsg in enumerate(filtered_messages):
            print(f"   Filtered {i+1} (score: {fmsg.priority_score}): {fmsg.message.text[:100]}...")
            print(f"     Filters: {fmsg.matched_filters}")
        
        if filtered_messages:
            # Generate digest
            print("\n🤖 Generating AI digest...")
            system_prompt = """You are a messaging digest assistant. Analyze the following Kleros messages and extract key information into structured JSON format. Focus on: urgent items, decisions made, important topics, people updates, calendar events, and unanswered mentions.

Respond with valid JSON matching this schema:
{
  "urgent": ["list of urgent items"],
  "decisions": ["decisions made or pending"],
  "topics": [{"topic": "string", "summary": "string", "participants": ["names"]}],
  "people_updates": [{"person": "name", "update": "what happened"}],
  "calendar": [{"event": "string", "date": "YYYY-MM-DD or relative", "time": "HH:MM or null"}],
  "unanswered_mentions": ["direct mentions or questions that need response"]
}"""
            
            digest_result = await digest_generator.generate_digest(
                filtered_messages, 
                system_prompt, 
                "daisugist"
            )
            
            if digest_result.success:
                print("✅ Digest generated successfully!")
                print("\n📋 Digest Text:")
                print(digest_result.digest_text)
                
                print("\n📊 Structured Data:")
                import json
                print(json.dumps(digest_result.structured_data, indent=2))
            else:
                print(f"❌ Digest generation failed: {digest_result.error_message}")
        else:
            print("ℹ️  No messages matched the filters")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await telegram_client.disconnect()
        print("🔌 Disconnected")

if __name__ == "__main__":
    asyncio.run(test_digest_processing())