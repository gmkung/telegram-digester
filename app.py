#!/usr/bin/env python3
"""
Telegram Digest Bot - Main Application
"""
import asyncio
import argparse
import logging
import os
import sys
import time
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from dotenv import load_dotenv

# Import our modules
from src.telegram_client import TelegramDigestClient
from src.message_processor import MessageProcessor
from src.digest_generator import DigestGenerator
from src.storage import StorageManager, DigestRun


# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,  # Enable debug logging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('digest_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TelegramDigestBot:
    """Main bot application"""
    
    def __init__(self, config_path: str = "config.yaml", watchlist_path: str = "watchlist.yml"):
        self.config_path = config_path
        self.watchlist_path = watchlist_path
        self.config = None
        self.watchlist = None
        
        # Components
        self.telegram_client = None
        self.message_processor = None
        self.digest_generator = None
        self.storage = None
        
        # Runtime state
        self.running = False
        self.last_config_load = None
        
        logger.info("Telegram Digest Bot initialized")
    
    def load_config(self) -> bool:
        """Load configuration files"""
        try:
            # Load main config
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            
            # Load watchlist
            with open(self.watchlist_path, 'r') as f:
                self.watchlist = yaml.safe_load(f)
            
            self.last_config_load = datetime.now()
            logger.info("Configuration loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return False
    
    def should_reload_config(self) -> bool:
        """Check if config should be reloaded (hot reload)"""
        if not self.last_config_load:
            return True
        
        try:
            config_mtime = os.path.getmtime(self.config_path)
            watchlist_mtime = os.path.getmtime(self.watchlist_path)
            
            config_time = datetime.fromtimestamp(config_mtime)
            watchlist_time = datetime.fromtimestamp(watchlist_mtime)
            
            return (config_time > self.last_config_load or 
                    watchlist_time > self.last_config_load)
                    
        except Exception as e:
            logger.error(f"Error checking config file times: {e}")
            return False
    
    async def initialize_components(self) -> bool:
        """Initialize all bot components"""
        try:
            # Initialize storage
            self.storage = StorageManager(self.config)
            
            # Initialize Telegram client
            telegram_config = self.config.get('telegram', {})
            self.telegram_client = TelegramDigestClient(telegram_config)
            await self.telegram_client.connect()
            self.telegram_client.load_watchlist(self.watchlist_path)
            
            # Initialize message processor
            digest_config = self.config.get('digest', {})
            self.message_processor = MessageProcessor(digest_config, self.watchlist)
            
            # Initialize digest generator
            self.digest_generator = DigestGenerator(self.config)
            
            # Validate LLM configuration
            if not self.digest_generator.llm_manager.validate_config():
                logger.error("LLM configuration validation failed")
                return False
            
            logger.info("All components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            return False
    
    async def run_digest_cycle(self) -> bool:
        """Run a single digest generation cycle"""
        start_time = time.time()
        
        try:
            logger.info("Starting digest cycle")
            
            # Collect messages from all watched chats
            max_messages_per_chat = self.config.get('digest', {}).get('max_messages_per_chat', 100)
            messages = await self.telegram_client.collect_messages_from_watchlist(
                max_messages_per_chat=max_messages_per_chat
            )
            
            if not messages:
                logger.info("No messages found")
                return True
            
            # Process messages (no filtering)
            username = None  # TODO: Get username from Telegram client
            filtered_messages = self.message_processor.filter_messages(messages, username)
            
            if not filtered_messages:
                logger.info("No messages to process")
                return True
            
            # Load system prompt
            system_prompt = self.load_system_prompt()
            
            # Generate digest
            digest_result = await self.digest_generator.generate_digest(
                filtered_messages, 
                system_prompt, 
                username
            )
            
            if not digest_result.success:
                logger.error(f"Digest generation failed: {digest_result.error_message}")
                return False
            
            # Save digest data
            digest_data = {
                "digest": digest_result.structured_data,
                "metadata": digest_result.metadata,
                "message_count": len(messages),
                "filtered_message_count": len(filtered_messages),
                "generated_at": datetime.now().isoformat()
            }
            
            self.storage.save_last_digest(digest_data)
            
            # Send to Telegram if configured
            if self.config.get('output', {}).get('send_to_saved_messages', True):
                await self.send_digest_to_telegram(digest_result, digest_data)
            
            # Export JSON if configured
            if self.config.get('output', {}).get('include_json_attachment', True):
                json_path = self.storage.export_digest_json(digest_data)
                logger.info(f"Digest JSON exported to {json_path}")
            
            processing_time = time.time() - start_time
            logger.info(f"Digest cycle completed successfully in {processing_time:.2f} seconds")
            return True
            
        except Exception as e:
            logger.error(f"Error during digest cycle: {e}")
            return False
    
    def load_system_prompt(self) -> str:
        """Load system prompt from file"""
        try:
            prompt_file = Path("prompts/digest_system.txt")
            with open(prompt_file, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            # Return a basic fallback prompt
            return """You are a messaging digest assistant. Analyze the messages and extract key information into JSON format with the following structure:
{
  "urgent": [],
  "decisions": [], 
  "topics": [],
  "people_updates": [],
  "calendar": [],
  "unanswered_mentions": []
}"""
    
    async def send_digest_to_telegram(self, digest_result, digest_data: Dict[str, Any]):
        """Send digest to Telegram Saved Messages"""
        try:
            # Format the message text
            message_text = digest_result.digest_text
            
            # Add metadata footer
            metadata = digest_result.metadata or {}
            footer = f"\n\n📊 **Stats**: {metadata.get('message_count', 0)} messages from {metadata.get('chat_count', 0)} chats"
            
            if metadata.get('validation_errors'):
                footer += f" ⚠️ {len(metadata['validation_errors'])} validation warnings"
            
            message_text += footer
            
            # Send to Saved Messages
            await self.telegram_client.send_to_saved_messages(message_text)
            
            logger.info("Digest sent to Telegram Saved Messages")
            
        except Exception as e:
            logger.error(f"Failed to send digest to Telegram: {e}")
            raise
    
    async def run_continuous(self):
        """Run the bot in continuous mode"""
        self.running = True
        interval_minutes = self.config.get('digest', {}).get('interval_minutes', 240)
        
        logger.info(f"Starting continuous mode with {interval_minutes} minute intervals")
        
        while self.running:
            try:
                # Check for config changes and reload if needed
                if self.should_reload_config():
                    logger.info("Configuration files changed, reloading...")
                    if self.load_config():
                        # Reinitialize components with new config
                        await self.cleanup()
                        await self.initialize_components()
                    else:
                        logger.error("Failed to reload configuration")
                
                # Run digest cycle
                await self.run_digest_cycle()
                
                # Clean up old backups periodically
                self.storage.cleanup_old_backups()
                
                # Wait for next cycle
                logger.info(f"Waiting {interval_minutes} minutes until next cycle...")
                
                # Sleep in smaller increments to allow for graceful shutdown
                sleep_seconds = interval_minutes * 60
                while sleep_seconds > 0 and self.running:
                    await asyncio.sleep(min(60, sleep_seconds))  # Check every minute
                    sleep_seconds -= 60
                    
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, stopping...")
                break
            except Exception as e:
                logger.error(f"Error in continuous mode: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(60)
        
        self.running = False
        logger.info("Continuous mode stopped")
    
    async def run_once(self):
        """Run digest generation once and exit"""
        logger.info("Running digest generation once")
        success = await self.run_digest_cycle()
        if success:
            logger.info("Single digest run completed successfully")
        else:
            logger.error("Single digest run failed")
        return success
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            if self.telegram_client:
                await self.telegram_client.disconnect()
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def stop(self):
        """Stop the bot"""
        self.running = False
        logger.info("Bot stop requested")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Telegram Digest Bot")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--config", default="config.yaml", help="Configuration file path")
    parser.add_argument("--watchlist", default="watchlist.yml", help="Watchlist file path") 
    parser.add_argument("--stats", action="store_true", help="Show storage statistics")
    parser.add_argument("--reset-cursors", nargs="*", help="Reset cursors for specified chats (or all if none specified)")
    
    args = parser.parse_args()
    
    # Create bot instance
    bot = TelegramDigestBot(args.config, args.watchlist)
    
    # Load configuration
    if not bot.load_config():
        logger.error("Failed to load configuration, exiting")
        sys.exit(1)
    
    # Handle special commands
    if args.stats:
        bot.storage = StorageManager(bot.config)
        stats = bot.storage.get_storage_stats()
        print("\n📊 Storage Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        sys.exit(0)
    
    if args.reset_cursors is not None:
        bot.storage = StorageManager(bot.config) 
        chat_ids = args.reset_cursors if args.reset_cursors else None
        success = bot.storage.reset_cursors(chat_ids)
        if success:
            if chat_ids:
                print(f"✅ Reset cursors for: {', '.join(chat_ids)}")
            else:
                print("✅ Reset all cursors")
        else:
            print("❌ Failed to reset cursors")
        sys.exit(0 if success else 1)
    
    try:
        # Initialize components
        if not await bot.initialize_components():
            logger.error("Failed to initialize bot components, exiting")
            sys.exit(1)
        
        # Run bot
        if args.once:
            success = await bot.run_once()
            sys.exit(0 if success else 1)
        else:
            await bot.run_continuous()
    
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await bot.cleanup()


if __name__ == "__main__":
    asyncio.run(main())