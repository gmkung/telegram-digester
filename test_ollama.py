#!/usr/bin/env python3
"""
Unit test for Ollama integration
Tests the actual Ollama API with real model calls
"""
import asyncio
import sys
from datetime import datetime, timezone
from llm import generate_digest, format_messages_for_llm


def create_test_messages():
    """Create sample messages for testing"""
    return [
        {
            'chat': '@kleros',
            'sender': 'Alice', 
            'time': datetime.now(timezone.utc),
            'text': 'URGENT: Smart contract audit results show critical vulnerability that needs immediate fix by Friday!'
        },
        {
            'chat': '@kleros',
            'sender': 'Bob',
            'time': datetime.now(timezone.utc), 
            'text': 'Meeting scheduled for tomorrow at 2 PM to discuss Q4 budget approval'
        },
        {
            'chat': 'SeedGov Kleros',
            'sender': 'Carol',
            'time': datetime.now(timezone.utc),
            'text': '@alice can you review the new partnership proposal with Uniswap?'
        },
        {
            'chat': 'SeedGov Kleros',
            'sender': 'David',
            'time': datetime.now(timezone.utc),
            'text': 'Just completed the integration with Compound protocol. Everything looks good!'
        }
    ]


def create_test_prompt():
    """Create test system prompt"""
    return """You are a messaging digest assistant. Analyze the messages and extract key information into JSON format with the following structure:
{
  "urgent": ["[Chat Name] High priority items"],
  "decisions": ["[Chat Name] Important decisions made"],
  "topics": [
    {
      "topic": "Topic name",
      "summary": "Brief summary",
      "participants": ["names"],
      "source_chat": "Chat Name"
    }
  ],
  "people_updates": [
    {
      "person": "Person's name",
      "update": "What happened",
      "source_chat": "Chat Name"
    }
  ],
  "calendar": [
    {
      "event": "[Chat Name] Event description",
      "date": "YYYY-MM-DD",
      "time": "HH:MM"
    }
  ],
  "unanswered_mentions": ["[Chat Name] Questions needing responses"]
}"""


async def test_ollama_integration():
    """Test Ollama integration with real API calls"""
    print("🧪 OLLAMA INTEGRATION TEST")
    print("=" * 50)
    
    # Test configuration
    ollama_config = {
        'provider': 'ollama',
        'ollama': {
            'base_url': 'http://localhost:11434',
            'model': 'mistral:latest',
            'temperature': 0.3,
            'top_p': 0.9
        }
    }
    
    # Create test data
    messages = create_test_messages()
    prompt = create_test_prompt()
    
    print(f"📊 Test Data:")
    print(f"  - Messages: {len(messages)}")
    print(f"  - Chats: {len(set(msg['chat'] for msg in messages))}")
    print(f"  - Model: {ollama_config['ollama']['model']}")
    
    # Test message formatting
    print(f"\n📝 Testing message formatting...")
    formatted_messages = format_messages_for_llm(messages)
    print(f"  ✅ Formatted {len(messages)} messages ({len(formatted_messages)} characters)")
    
    # Test Ollama API call
    print(f"\n🤖 Testing Ollama API call...")
    try:
        start_time = datetime.now()
        
        digest_result = await generate_digest(messages, prompt, ollama_config)
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        print(f"  ✅ Ollama response received in {processing_time:.2f} seconds")
        
        # Validate response structure
        print(f"\n🔍 Validating response structure...")
        required_keys = ['urgent', 'decisions', 'topics', 'people_updates', 'calendar', 'unanswered_mentions']
        
        for key in required_keys:
            if key in digest_result:
                print(f"  ✅ {key}: {len(digest_result[key])} items")
            else:
                print(f"  ❌ Missing key: {key}")
                return False
        
        # Check for actual content
        print(f"\n📋 Content Analysis:")
        total_items = sum(len(digest_result[key]) for key in required_keys if isinstance(digest_result[key], list))
        print(f"  - Total extracted items: {total_items}")
        
        if digest_result['urgent']:
            print(f"  - Urgent items: {digest_result['urgent']}")
        
        if digest_result['calendar']:
            print(f"  - Calendar events: {digest_result['calendar']}")
            
        if digest_result['unanswered_mentions']:
            print(f"  - Unanswered mentions: {digest_result['unanswered_mentions']}")
        
        # Check for chat attribution
        print(f"\n🏷️  Testing chat attribution...")
        has_attribution = False
        
        for item in digest_result['urgent']:
            if '[' in item and ']' in item:
                has_attribution = True
                break
        
        if has_attribution:
            print(f"  ✅ Chat attribution found in urgent items")
        else:
            print(f"  ⚠️  Chat attribution may be missing")
        
        print(f"\n🎉 OLLAMA INTEGRATION TEST PASSED!")
        return True
        
    except Exception as e:
        print(f"  ❌ Error during Ollama API call: {e}")
        return False


async def main():
    """Main test runner"""
    try:
        success = await test_ollama_integration()
        if success:
            print(f"\n✅ All tests passed! Ollama integration is working correctly.")
            sys.exit(0)
        else:
            print(f"\n❌ Tests failed! Check Ollama configuration.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n⏹️  Test interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())