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

# Setup basic logging (will be reconfigured after config load)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
            
            # Configure logging based on config
            self._setup_logging()
            
            self.last_config_load = datetime.now()
            logger.info("Configuration loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return False
    
    def _setup_logging(self):
        """Setup logging based on configuration"""
        try:
            log_config = self.config.get('logging', {})
            log_level = getattr(logging, log_config.get('level', 'INFO').upper())
            
            # Clear existing handlers
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # Create formatter
            formatter = logging.Formatter(log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            
            # Add file handler if enabled
            if log_config.get('file_logging', True):
                file_handler = logging.FileHandler('digest_bot.log')
                file_handler.setFormatter(formatter)
                file_handler.setLevel(log_level)
                root_logger.addHandler(file_handler)
            
            # Add console handler if enabled
            if log_config.get('console_logging', True):
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                console_handler.setLevel(log_level)
                root_logger.addHandler(console_handler)
            
            # Set root logger level
            root_logger.setLevel(log_level)
            
            logger.info(f"Logging configured: level={log_config.get('level', 'INFO')}, file={log_config.get('file_logging', True)}, console={log_config.get('console_logging', True)}")
            
        except Exception as e:
            # Fallback to basic logging if config fails
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('digest_bot.log'),
                    logging.StreamHandler(sys.stdout)
                ]
            )
            logger.warning(f"Failed to configure logging from config, using fallback: {e}")
    
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
            
            # Calculate cutoff time for server-side filtering
            from datetime import datetime, timedelta, timezone
            digest_config = self.config.get('digest', {})
            lookback_hours = digest_config.get('lookback_hours', 72)
            local_cutoff = datetime.now().astimezone() - timedelta(hours=lookback_hours)
            cutoff_time = local_cutoff.astimezone(timezone.utc)
            logger.info(f"Lookback filter: {lookback_hours} hours ago = {cutoff_time} UTC (local: {local_cutoff})")
            
            # Process each chat individually
            username = None  # TODO: Get username from Telegram client
            system_prompt = self.load_system_prompt()
            all_chat_summaries = []
            
            # Get watchlist for individual processing
            watchlist_config = self.telegram_client.watchlist.get('watchlist', {})
            
            # Process channels
            for channel_config in watchlist_config.get('channels', []):
                if not channel_config.get('enabled', True):
                    continue
                    
                chat_summary = await self._process_single_chat(
                    channel_config['name'], 
                    channel_config.get('max_messages', 100),
                    cutoff_time, 
                    username, 
                    system_prompt,
                    is_channel=True
                )
                if chat_summary:
                    all_chat_summaries.append(chat_summary)
            
            # Process private chats
            for chat_config in watchlist_config.get('chats', []):
                if not chat_config.get('enabled', True):
                    continue
                    
                chat_identifier = chat_config.get('chat_id') or chat_config.get('name')
                if not chat_identifier:
                    continue
                    
                chat_summary = await self._process_single_chat(
                    chat_identifier, 
                    chat_config.get('max_messages', 100),
                    cutoff_time, 
                    username, 
                    system_prompt,
                    is_channel=False
                )
                if chat_summary:
                    all_chat_summaries.append(chat_summary)
            
            # Create final JSON summary of all chats
            if all_chat_summaries:
                await self._create_final_summary(all_chat_summaries)
                processing_time = time.time() - start_time
                logger.info(f"Processed {len(all_chat_summaries)} chats successfully in {processing_time:.2f} seconds")
            else:
                logger.info("No chats had messages to process")
            
            return True
            
        except Exception as e:
            logger.error(f"Error during digest cycle: {e}")
            return False
    
    async def _process_single_chat(self, chat_identifier: str, max_messages: int, cutoff_time, username: str, system_prompt: str, is_channel: bool) -> dict:
        """Process a single chat: retrieve, filter, generate digest, send to Saved Messages"""
        try:
            logger.info(f"Processing {'channel' if is_channel else 'chat'}: {chat_identifier}")
            
            # Retrieve messages for this chat
            messages = await self.telegram_client.get_chat_messages(
                chat_identifier, 
                limit=max_messages, 
                offset_date=cutoff_time
            )
            
            if not messages:
                logger.info(f"No messages found for {chat_identifier}")
                return None
            
            # Filter messages
            filtered_messages = self.message_processor.filter_messages(messages, username)
            
            if not filtered_messages:
                logger.info(f"No relevant messages found for {chat_identifier}")
                return None
            
            # Generate digest
            digest_result = await self.digest_generator.generate_digest(
                filtered_messages, 
                system_prompt, 
                username
            )
            
            if not digest_result.success:
                logger.error(f"Failed to generate digest for {chat_identifier}: {digest_result.error_message}")
                return None
            
            # Send to Saved Messages
            if self.config.get('output', {}).get('send_to_saved_messages', True):
                await self.send_digest_to_telegram(digest_result, {
                    "chat_name": chat_identifier,
                    "message_count": len(messages),
                    "filtered_message_count": len(filtered_messages)
                })
            
            # Return summary for final JSON
            return {
                "chat_name": chat_identifier,
                "is_channel": is_channel,
                "message_count": len(messages),
                "filtered_message_count": len(filtered_messages),
                "digest": digest_result.structured_data,
                "processed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error processing {chat_identifier}: {e}")
            return None
    
    async def _create_final_summary(self, all_chat_summaries: list):
        """Create and save final JSON summary of all processed chats"""
        try:
            summary_data = {
                "generated_at": datetime.now().isoformat(),
                "total_chats_processed": len(all_chat_summaries),
                "total_messages": sum(chat["message_count"] for chat in all_chat_summaries),
                "total_filtered_messages": sum(chat["filtered_message_count"] for chat in all_chat_summaries),
                "chats": all_chat_summaries
            }
            
            # Save to storage
            self.storage.save_last_digest(summary_data)
            
            # Export JSON if configured
            if self.config.get('output', {}).get('include_json_attachment', True):
                json_path = self.storage.export_digest_json(summary_data)
                logger.info(f"Final digest summary JSON exported to {json_path}")
            
        except Exception as e:
            logger.error(f"Error creating final summary: {e}")
    
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
        """Send digest to Telegram Saved Messages as individual chat messages"""
        try:
            # Get the chat digests from the metadata
            metadata = digest_result.metadata or {}
            chat_details = metadata.get('chat_details', {})
            
            if not chat_details:
                # Fallback: send as single message if no chat details
                message_text = digest_result.digest_text
                footer = f"\n\n📊 **Stats**: {metadata.get('message_count', 0)} messages from {metadata.get('chat_count', 0)} chats"
                if metadata.get('validation_errors'):
                    footer += f" ⚠️ {len(metadata['validation_errors'])} validation warnings"
                message_text += footer
                
                await self.telegram_client.send_to_saved_messages(message_text)
                logger.info("Digest sent to Telegram Saved Messages (single message)")
                return
            
            # Send individual chat digests
            total_sent = 0
            for chat_name, chat_data in chat_details.items():
                try:
                    # Generate individual chat digest text
                    chat_digest_text = self._format_single_chat_digest(
                        chat_name, 
                        chat_data, 
                        digest_result.structured_data,
                        metadata
                    )
                    
                    if chat_digest_text.strip():
                        await self.telegram_client.send_to_saved_messages(chat_digest_text)
                        total_sent += 1
                        logger.info(f"Sent digest for chat: {chat_name}")
                        
                        # Small delay between messages to avoid rate limiting
                        await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Failed to send digest for chat {chat_name}: {e}")
            
            # Send summary message
            summary_text = self._format_digest_summary(metadata, total_sent)
            await self.telegram_client.send_to_saved_messages(summary_text)
            
            logger.info(f"Successfully sent {total_sent} individual chat digests + summary to Telegram Saved Messages")
            
        except Exception as e:
            logger.error(f"Failed to send digest to Telegram: {e}")
            raise
    
    def _format_single_chat_digest(self, chat_name: str, chat_data: Dict[str, Any], 
                                  structured_data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
        """Format digest for a single chat using the actual structured data"""
        # Extract chat-specific data from the combined structured_data
        # The structured_data contains all chats combined, so we need to filter by source_chat
        chat_structured_data = {
            "urgent": [],
            "decisions": [],
            "topics": [],
            "people_updates": [],
            "calendar": [],
            "unanswered_mentions": []
        }
        
        # Filter urgent items for this chat
        if structured_data.get("urgent"):
            for item in structured_data["urgent"]:
                if f"[{chat_name}]" in item:
                    # Remove the chat prefix for display
                    clean_item = item.replace(f"[{chat_name}] ", "")
                    chat_structured_data["urgent"].append(clean_item)
        
        # Filter decisions for this chat
        if structured_data.get("decisions"):
            for decision in structured_data["decisions"]:
                if f"[{chat_name}]" in decision:
                    clean_decision = decision.replace(f"[{chat_name}] ", "")
                    chat_structured_data["decisions"].append(clean_decision)
        
        # Filter topics for this chat
        if structured_data.get("topics"):
            for topic in structured_data["topics"]:
                if topic.get("source_chat") == chat_name:
                    # Remove source_chat for display
                    topic_copy = topic.copy()
                    topic_copy.pop("source_chat", None)
                    chat_structured_data["topics"].append(topic_copy)
        
        # Filter people updates for this chat
        if structured_data.get("people_updates"):
            for update in structured_data["people_updates"]:
                if update.get("source_chat") == chat_name:
                    # Remove source_chat for display
                    update_copy = update.copy()
                    update_copy.pop("source_chat", None)
                    chat_structured_data["people_updates"].append(update_copy)
        
        # Filter calendar events for this chat
        if structured_data.get("calendar"):
            for event in structured_data["calendar"]:
                if event.get("source_chat") == chat_name:
                    # Remove source_chat for display
                    event_copy = event.copy()
                    event_copy.pop("source_chat", None)
                    chat_structured_data["calendar"].append(event_copy)
        
        # Filter unanswered mentions for this chat
        if structured_data.get("unanswered_mentions"):
            for mention in structured_data["unanswered_mentions"]:
                if f"[{chat_name}]" in mention:
                    clean_mention = mention.replace(f"[{chat_name}] ", "")
                    chat_structured_data["unanswered_mentions"].append(clean_mention)
        
        # Create header
        header = f"📱 **{chat_name}** Digest\n"
        header += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        header += f"💬 {chat_data.get('message_count', 0)} messages\n"
        header += "=" * 50 + "\n\n"
        
        sections = []
        
        # Add validation errors if any
        validation_errors = chat_data.get('validation_errors', [])
        if validation_errors:
            sections.append("⚠️ **Validation Issues:**")
            for error in validation_errors:
                sections.append(f"• {error}")
            sections.append("")
        
        # Check if this chat has any significant content
        has_content = any([
            chat_structured_data.get("urgent"),
            chat_structured_data.get("decisions"),
            chat_structured_data.get("topics"),
            chat_structured_data.get("people_updates"),
            chat_structured_data.get("calendar"),
            chat_structured_data.get("unanswered_mentions")
        ])
        
        if not has_content:
            sections.append("💤 **No significant updates in this chat**")
            sections.append("This chat had messages but no actionable content was identified.")
        else:
            # Add urgent items
            if chat_structured_data.get("urgent"):
                sections.append("🚨 **URGENT ITEMS**")
                for item in chat_structured_data["urgent"]:
                    sections.append(f"• {item}")
                sections.append("")
            
            # Add unanswered mentions
            if chat_structured_data.get("unanswered_mentions"):
                sections.append("💬 **REQUIRES YOUR RESPONSE**")
                for mention in chat_structured_data["unanswered_mentions"]:
                    sections.append(f"• {mention}")
                sections.append("")
            
            # Add calendar events
            if chat_structured_data.get("calendar"):
                sections.append("📅 **CALENDAR & DEADLINES**")
                for event in chat_structured_data["calendar"]:
                    time_str = f" at {event['time']}" if event.get("time") else ""
                    sections.append(f"• {event['event']} - {event['date']}{time_str}")
                sections.append("")
            
            # Add decisions
            if chat_structured_data.get("decisions"):
                sections.append("✅ **DECISIONS MADE**")
                for decision in chat_structured_data["decisions"]:
                    sections.append(f"• {decision}")
                sections.append("")
            
            # Add topics
            if chat_structured_data.get("topics"):
                sections.append("💡 **KEY TOPICS DISCUSSED**")
                for topic in chat_structured_data["topics"]:
                    participants = ""
                    if topic.get("participants"):
                        participants = f" (👥 {', '.join(topic['participants'])})"
                    sections.append(f"• **{topic['topic']}**{participants}")
                    sections.append(f"  {topic['summary']}")
                sections.append("")
            
            # Add people updates
            if chat_structured_data.get("people_updates"):
                sections.append("👥 **PEOPLE UPDATES**")
                for update in chat_structured_data["people_updates"]:
                    sections.append(f"• **{update['person']}**: {update['update']}")
                sections.append("")
        
        return header + "\n".join(sections)
    
    def _format_digest_summary(self, metadata: Dict[str, Any], total_sent: int) -> str:
        """Format summary message for all digests"""
        summary = "📊 **Digest Summary**\n"
        summary += "=" * 30 + "\n\n"
        
        summary += f"📱 **Total Chats Processed:** {metadata.get('chat_count', 0)}\n"
        summary += f"💬 **Total Messages:** {metadata.get('message_count', 0)}\n"
        summary += f"📤 **Digests Sent:** {total_sent}\n"
        
        if metadata.get('validation_errors'):
            summary += f"⚠️ **Validation Warnings:** {len(metadata['validation_errors'])}\n"
        
        summary += f"\n🕐 **Generated:** {metadata.get('generated_at', 'Unknown')}\n"
        summary += f"🤖 **LLM Provider:** {metadata.get('llm_provider', 'Unknown')}\n"
        
        return summary
    
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
        try:
            success = await self.run_digest_cycle()
            if success:
                logger.info("Single digest run completed successfully")
            else:
                logger.error("Single digest run failed")
            return success
        finally:
            # Immediately disconnect after digest completion for --once mode
            logger.info("Disconnecting immediately after digest completion")
            if self.telegram_client:
                await self.telegram_client.disconnect()
    
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
            # For --once mode, disconnect immediately and exit
            await bot.cleanup()
            sys.exit(0 if success else 1)
        else:
            await bot.run_continuous()
    
    except KeyboardInterrupt:
        logger.info("Received interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Only cleanup if not in --once mode (already cleaned up above)
        if not args.once:
            await bot.cleanup()


if __name__ == "__main__":
    asyncio.run(main())