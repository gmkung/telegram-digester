#!/usr/bin/env python3
"""
Simple Telegram Digest Bot
Collects messages from monitored chats, processes with AI, and sends digests
"""
import asyncio
import sys
from config import load_config
from telegram import collect_messages, send_summary
from llm import generate_digest
from output import create_markdown_file, format_telegram_summary


async def main():
    """Main orchestration function"""
    print("🤖 Starting Telegram Digest Bot")
    
    try:
        # Load configuration
        print("📋 Loading configuration...")
        config = load_config()
        
        # Collect messages from monitored chats
        print("📥 Collecting messages from Telegram...")
        messages = await collect_messages(
            config['watchlist'], 
            config['settings']['hours_back'],
            config['telegram']
        )
        
        if not messages:
            print("📭 No messages found in the specified time range")
            summary_text = "🔔 Digest: No activity in monitored chats"
            await send_summary(summary_text, config['telegram'])
            return
        
        print(f"📊 Processing {len(messages)} messages with AI...")
        
        # Generate digest using LLM
        digest_data = await generate_digest(
            messages, 
            config['prompt'],
            config['llm']
        )
        
        # Create markdown file
        print("📝 Creating markdown digest...")
        markdown_file = create_markdown_file(
            digest_data, 
            config['settings']['output_dir']
        )
        
        # Generate chat URLs from messages
        chat_urls = {}
        for msg in messages:
            if msg.get('chat_url'):
                chat_urls[msg['chat']] = msg['chat_url']
        
        # Format concise summary for Telegram
        print("📱 Sending summary to Telegram...")
        summary_text = format_telegram_summary(digest_data, chat_urls)
        await send_summary(summary_text, config['telegram'])
        
        print("✅ Digest generation completed successfully!")
        if markdown_file:
            print(f"📄 Full digest saved to: {markdown_file}")
            
    except KeyboardInterrupt:
        print("\n⏹️  Process interrupted by user")
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ Error during digest generation: {e}")
        sys.exit(1)


def run_once():
    """Run digest generation once and exit"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Process interrupted")
        sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("""Simple Telegram Digest Bot

Usage:
  python main.py          Run digest generation once
  python main.py --help   Show this help message

Configuration:
  Edit config.yaml and watchlist.yaml to configure the bot
  Set TELEGRAM_API_ID, TELEGRAM_API_HASH, and OPENAI_API_KEY environment variables
        """)
        sys.exit(0)
    
    run_once()