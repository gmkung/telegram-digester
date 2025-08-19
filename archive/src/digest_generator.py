"""
Digest generation with JSON schema validation
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from src.llm_providers import LLMManager
from src.message_processor import FilteredMessage


logger = logging.getLogger(__name__)


@dataclass
class DigestResult:
    """Result of digest generation"""
    success: bool
    digest_text: str
    structured_data: Dict[str, Any]
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = None


class DigestGenerator:
    """Generate structured digests from filtered messages"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_manager = LLMManager(config.get('llm', {}))
        
        # JSON schema for validation
        self.digest_schema = {
            "type": "object",
            "properties": {
                "urgent": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of urgent items requiring immediate attention"
                },
                "decisions": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "Important decisions made or pending"
                },
                "topics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "summary": {"type": "string"},
                            "participants": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["topic", "summary"]
                    },
                    "description": "Important topics discussed with summaries"
                },
                "people_updates": {
                    "type": "array",
                    "items": {
                        "type": "object", 
                        "properties": {
                            "person": {"type": "string"},
                            "update": {"type": "string"}
                        },
                        "required": ["person", "update"]
                    },
                    "description": "Updates about specific people"
                },
                "calendar": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event": {"type": "string"},
                            "date": {"type": "string"},
                            "time": {"type": ["string", "null"]}
                        },
                        "required": ["event", "date"]
                    },
                    "description": "Calendar events and deadlines"
                },
                "unanswered_mentions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Direct mentions or questions that need response"
                }
            },
            "required": ["urgent", "decisions", "topics", "people_updates", "calendar", "unanswered_mentions"]
        }
    
    async def generate_digest(
        self, 
        filtered_messages: List[FilteredMessage],
        system_prompt: str,
        username: Optional[str] = None
    ) -> DigestResult:
        """Generate a digest from filtered messages"""
        try:
            if not filtered_messages:
                return DigestResult(
                    success=True,
                    digest_text="No new messages to digest.",
                    structured_data={
                        "urgent": [],
                        "decisions": [],
                        "topics": [],
                        "people_updates": [],
                        "calendar": [],
                        "unanswered_mentions": []
                    },
                    metadata={"message_count": 0, "generated_at": datetime.now().isoformat()}
                )
            
            # Group messages by chat
            chat_messages = {}
            for msg in filtered_messages:
                chat_name = msg.message.chat_name
                if chat_name not in chat_messages:
                    chat_messages[chat_name] = []
                chat_messages[chat_name].append(msg)
            
            logger.info(f"Generating per-chat digests for {len(chat_messages)} chats with {len(filtered_messages)} total messages")
            
            # Generate digest for each chat separately
            chat_digests = {}
            for chat_name, messages in chat_messages.items():
                logger.info(f"Processing chat: {chat_name} ({len(messages)} messages)")
                
                # Format messages for this specific chat
                from src.message_processor import MessageProcessor
                processor = MessageProcessor(self.config.get('digest', {}), {})
                messages_text = processor.format_messages_for_llm(messages)
                
                # Customize system prompt with username if provided
                chat_system_prompt = system_prompt
                if username:
                    chat_system_prompt = chat_system_prompt.replace("{username}", username)
                else:
                    chat_system_prompt = chat_system_prompt.replace("{username}", "you")
                
                # Generate digest for this chat
                try:
                    structured_data = await self.llm_manager.generate_digest(messages_text, chat_system_prompt)
                    
                    # Validate JSON schema
                    validation_result = self._validate_digest_schema(structured_data)
                    if not validation_result["valid"]:
                        logger.warning(f"Chat {chat_name} schema validation failed: {validation_result['errors']}")
                        # Attempt to fix common issues
                        structured_data = self._fix_digest_schema(structured_data)
                    
                    chat_digests[chat_name] = {
                        "structured_data": structured_data,
                        "message_count": len(messages),
                        "validation_errors": validation_result.get("errors", []) if not validation_result["valid"] else []
                    }
                    
                except Exception as e:
                    logger.error(f"Failed to generate digest for chat {chat_name}: {e}")
                    # Create fallback digest for this chat
                    chat_digests[chat_name] = {
                        "structured_data": {
                            "urgent": [],
                            "decisions": [],
                            "topics": [],
                            "people_updates": [],
                            "calendar": [],
                            "unanswered_mentions": []
                        },
                        "message_count": len(messages),
                        "validation_errors": [f"Failed to process: {str(e)}"]
                    }
            
            # Combine all chat digests into one comprehensive digest
            combined_digest = self._combine_chat_digests(chat_digests)
            
            # Generate human-readable digest text
            digest_text = self._format_multi_chat_digest_text(chat_digests)
            
            # Create metadata
            metadata = {
                "message_count": len(filtered_messages),
                "generated_at": datetime.now().isoformat(),
                "llm_provider": self.llm_manager.get_provider_info(),
                "chat_count": len(chat_messages),
                "high_priority_count": 0,
                "validation_errors": [err for chat in chat_digests.values() for err in chat.get("validation_errors", [])],
                "chat_details": {name: {"message_count": data["message_count"], "validation_errors": data["validation_errors"]} 
                                for name, data in chat_digests.items()}
            }
            
            return DigestResult(
                success=True,
                digest_text=digest_text,
                structured_data=combined_digest,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Failed to generate digest: {e}")
            return DigestResult(
                success=False,
                digest_text="Failed to generate digest due to error.",
                structured_data={},
                error_message=str(e),
                metadata={"message_count": len(filtered_messages), "error_at": datetime.now().isoformat()}
            )
    
    def _validate_digest_schema(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate digest data against schema"""
        try:
            # Basic structure validation
            required_fields = ["urgent", "decisions", "topics", "people_updates", "calendar", "unanswered_mentions"]
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                return {
                    "valid": False,
                    "errors": [f"Missing required fields: {missing_fields}"]
                }
            
            errors = []
            
            # Validate array fields
            array_fields = ["urgent", "decisions", "unanswered_mentions"]
            for field in array_fields:
                if not isinstance(data[field], list):
                    errors.append(f"Field '{field}' must be an array")
            
            # Validate complex object arrays
            if not isinstance(data["topics"], list):
                errors.append("Field 'topics' must be an array")
            else:
                for i, topic in enumerate(data["topics"]):
                    if not isinstance(topic, dict):
                        errors.append(f"topics[{i}] must be an object")
                    elif "topic" not in topic or "summary" not in topic:
                        errors.append(f"topics[{i}] missing required fields 'topic' or 'summary'")
            
            if not isinstance(data["people_updates"], list):
                errors.append("Field 'people_updates' must be an array")
            else:
                for i, update in enumerate(data["people_updates"]):
                    if not isinstance(update, dict):
                        errors.append(f"people_updates[{i}] must be an object")
                    elif "person" not in update or "update" not in update:
                        errors.append(f"people_updates[{i}] missing required fields 'person' or 'update'")
            
            if not isinstance(data["calendar"], list):
                errors.append("Field 'calendar' must be an array")
            else:
                for i, event in enumerate(data["calendar"]):
                    if not isinstance(event, dict):
                        errors.append(f"calendar[{i}] must be an object")
                    elif "event" not in event or "date" not in event:
                        errors.append(f"calendar[{i}] missing required fields 'event' or 'date'")
            
            return {
                "valid": len(errors) == 0,
                "errors": errors
            }
            
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Schema validation error: {str(e)}"]
            }
    
    def _fix_digest_schema(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to fix common schema issues"""
        fixed_data = data.copy()
        
        # Handle case where Ollama returns a different structure
        if "messages" in data and isinstance(data["messages"], list):
            logger.warning("Ollama returned 'messages' structure instead of expected format, attempting to extract content")
            # Try to extract meaningful content from the messages
            message_text = ""
            for msg in data["messages"]:
                if isinstance(msg, dict) and "text" in msg:
                    message_text += str(msg["text"]) + "\n"
            
            # Create a basic structure with the extracted content
            fixed_data = {
                "urgent": [],
                "decisions": [],
                "topics": [{
                    "topic": "General Discussion",
                    "summary": message_text[:500] + "..." if len(message_text) > 500 else message_text,
                    "participants": []
                }],
                "people_updates": [],
                "calendar": [],
                "unanswered_mentions": []
            }
            
            # Try to extract some structure from the text
            if "urgent" in message_text.lower() or "asap" in message_text.lower():
                fixed_data["urgent"].append("Content marked as urgent found in messages")
            
            if "decision" in message_text.lower() or "decided" in message_text.lower():
                fixed_data["decisions"].append("Decision-related content found in messages")
            
            if "meeting" in message_text.lower() or "deadline" in message_text.lower():
                fixed_data["calendar"].append({
                    "event": "Meeting or deadline mentioned",
                    "date": "Check messages for details",
                    "time": None
                })
            
            return fixed_data
        
        # Ensure all required fields exist with correct types
        required_arrays = ["urgent", "decisions", "unanswered_mentions"]
        for field in required_arrays:
            if field not in fixed_data or not isinstance(fixed_data[field], list):
                fixed_data[field] = []
        
        # Fix topics array
        if "topics" not in fixed_data or not isinstance(fixed_data["topics"], list):
            fixed_data["topics"] = []
        else:
            fixed_topics = []
            for topic in fixed_data["topics"]:
                if isinstance(topic, dict) and "topic" in topic and "summary" in topic:
                    fixed_topic = {
                        "topic": str(topic["topic"]),
                        "summary": str(topic["summary"]),
                        "participants": topic.get("participants", []) if isinstance(topic.get("participants"), list) else []
                    }
                    fixed_topics.append(fixed_topic)
            fixed_data["topics"] = fixed_topics
        
        # Fix people_updates array
        if "people_updates" not in fixed_data or not isinstance(fixed_data["people_updates"], list):
            fixed_data["people_updates"] = []
        else:
            fixed_updates = []
            for update in fixed_data["people_updates"]:
                if isinstance(update, dict) and "person" in update and "update" in update:
                    fixed_update = {
                        "person": str(update["person"]),
                        "update": str(update["update"])
                    }
                    fixed_updates.append(fixed_update)
            fixed_data["people_updates"] = fixed_updates
        
        # Fix calendar array
        if "calendar" not in fixed_data or not isinstance(fixed_data["calendar"], list):
            fixed_data["calendar"] = []
        else:
            fixed_calendar = []
            for event in fixed_data["calendar"]:
                if isinstance(event, dict) and "event" in event and "date" in event:
                    fixed_event = {
                        "event": str(event["event"]),
                        "date": str(event["date"]),
                        "time": event.get("time") if event.get("time") else None
                    }
                    fixed_calendar.append(fixed_event)
            fixed_data["calendar"] = fixed_calendar
        
        return fixed_data
    
    def _combine_chat_digests(self, chat_digests: Dict[str, Any]) -> Dict[str, Any]:
        """Combine individual chat digests into one comprehensive digest"""
        combined = {
            "urgent": [],
            "decisions": [],
            "topics": [],
            "people_updates": [],
            "calendar": [],
            "unanswered_mentions": []
        }
        
        for chat_name, chat_data in chat_digests.items():
            structured_data = chat_data["structured_data"]
            
            # Combine urgent items
            if structured_data.get("urgent"):
                for item in structured_data["urgent"]:
                    combined["urgent"].append(f"[{chat_name}] {item}")
            
            # Combine decisions
            if structured_data.get("decisions"):
                for decision in structured_data["decisions"]:
                    combined["decisions"].append(f"[{chat_name}] {decision}")
            
            # Combine topics
            if structured_data.get("topics"):
                for topic in structured_data["topics"]:
                    topic_copy = topic.copy()
                    topic_copy["source_chat"] = chat_name
                    combined["topics"].append(topic_copy)
            
            # Combine people updates
            if structured_data.get("people_updates"):
                for update in structured_data["people_updates"]:
                    update_copy = update.copy()
                    update_copy["source_chat"] = chat_name
                    combined["people_updates"].append(update_copy)
            
            # Combine calendar events
            if structured_data.get("calendar"):
                for event in structured_data["calendar"]:
                    event_copy = event.copy()
                    event_copy["source_chat"] = chat_name
                    combined["calendar"].append(event_copy)
            
            # Combine unanswered mentions
            if structured_data.get("unanswered_mentions"):
                for mention in structured_data["unanswered_mentions"]:
                    combined["unanswered_mentions"].append(f"[{chat_name}] {mention}")
        
        return combined
    
    def _format_multi_chat_digest_text(self, chat_digests: Dict[str, Any]) -> str:
        """Format multi-chat digest text with per-chat sections"""
        sections = []
        
        # Add header
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"📊 **Multi-Chat Digest** - {timestamp}\n" + "=" * 50 + "\n\n"
        sections.append(header)
        
        # Process each chat
        for chat_name, chat_data in chat_digests.items():
            structured_data = chat_data["structured_data"]
            message_count = chat_data["message_count"]
            
            # Check if this chat has any significant content
            has_content = any([
                structured_data.get("urgent"),
                structured_data.get("decisions"),
                structured_data.get("topics"),
                structured_data.get("people_updates"),
                structured_data.get("calendar"),
                structured_data.get("unanswered_mentions")
            ])
            
            # Add chat header
            sections.append(f"## 📱 **{chat_name}** ({message_count} messages)")
            
            if not has_content:
                sections.append("💤 *No significant updates in this chat*\n")
                continue
            
            # Add urgent items
            if structured_data.get("urgent"):
                sections.append("🚨 **URGENT ITEMS**")
                for item in structured_data["urgent"]:
                    sections.append(f"• {item}")
                sections.append("")
            
            # Add unanswered mentions
            if structured_data.get("unanswered_mentions"):
                sections.append("💬 **REQUIRES YOUR RESPONSE**")
                for mention in structured_data["unanswered_mentions"]:
                    sections.append(f"• {mention}")
                sections.append("")
            
            # Add calendar events
            if structured_data.get("calendar"):
                sections.append("📅 **CALENDAR & DEADLINES**")
                for event in structured_data["calendar"]:
                    time_str = f" at {event['time']}" if event.get("time") else ""
                    sections.append(f"• {event['event']} - {event['date']}{time_str}")
                sections.append("")
            
            # Add decisions
            if structured_data.get("decisions"):
                sections.append("✅ **DECISIONS MADE**")
                for decision in structured_data["decisions"]:
                    sections.append(f"• {decision}")
                sections.append("")
            
            # Add topics
            if structured_data.get("topics"):
                sections.append("💡 **KEY TOPICS DISCUSSED**")
                for topic in structured_data["topics"]:
                    participants = ""
                    if topic.get("participants"):
                        participants = f" (👥 {', '.join(topic['participants'])})"
                    sections.append(f"• **{topic['topic']}**{participants}")
                    sections.append(f"  {topic['summary']}")
                sections.append("")
            
            # Add people updates
            if structured_data.get("people_updates"):
                sections.append("👥 **PEOPLE UPDATES**")
                for update in structured_data["people_updates"]:
                    sections.append(f"• **{update['person']}**: {update['update']}")
                sections.append("")
            
            sections.append("---\n")  # Separator between chats
        
        # Add footer
        total_messages = sum(chat_data["message_count"] for chat_data in chat_digests.values())
        total_chats = len(chat_digests)
        footer = f"\n📊 **Summary**: {total_messages} messages from {total_chats} chats"
        
        # Add validation warnings if any
        all_errors = [err for chat_data in chat_digests.values() for err in chat_data.get("validation_errors", [])]
        if all_errors:
            footer += f" ⚠️ {len(all_errors)} validation warnings"
        
        sections.append(footer)
        
        return "\n".join(sections)
    
    def _format_digest_text(self, structured_data: Dict[str, Any]) -> str:
        """Format structured data into human-readable digest text"""
        sections = []
        
        # Debug logging
        logger.debug(f"Formatting digest text with data: {list(structured_data.keys())}")
        logger.debug(f"Urgent items: {structured_data.get('urgent', [])}")
        logger.debug(f"Decisions: {structured_data.get('decisions', [])}")
        logger.debug(f"Topics: {len(structured_data.get('topics', []))}")
        logger.debug(f"People updates: {len(structured_data.get('people_updates', []))}")
        logger.debug(f"Unanswered mentions: {structured_data.get('unanswered_mentions', [])}")
        
        # Urgent items
        if structured_data.get("urgent"):
            sections.append("🚨 **URGENT ITEMS**")
            for item in structured_data["urgent"]:
                sections.append(f"• {item}")
            sections.append("")
        
        # Unanswered mentions
        if structured_data.get("unanswered_mentions"):
            sections.append("💬 **REQUIRES YOUR RESPONSE**")
            for mention in structured_data["unanswered_mentions"]:
                sections.append(f"• {mention}")
            sections.append("")
        
        # Calendar events
        if structured_data.get("calendar"):
            sections.append("📅 **CALENDAR & DEADLINES**")
            for event in structured_data["calendar"]:
                time_str = f" at {event['time']}" if event.get("time") else ""
                sections.append(f"• {event['event']} - {event['date']}{time_str}")
            sections.append("")
        
        # Decisions
        if structured_data.get("decisions"):
            sections.append("✅ **DECISIONS MADE**")
            for decision in structured_data["decisions"]:
                sections.append(f"• {decision}")
            sections.append("")
        
        # Topics
        if structured_data.get("topics"):
            sections.append("💡 **KEY TOPICS DISCUSSED**")
            for topic in structured_data["topics"]:
                participants = ""
                if topic.get("participants"):
                    participants = f" (👥 {', '.join(topic['participants'])})"
                sections.append(f"• **{topic['topic']}**{participants}")
                sections.append(f"  {topic['summary']}")
            sections.append("")
        
        # People updates
        if structured_data.get("people_updates"):
            sections.append("👥 **PEOPLE UPDATES**")
            for update in structured_data["people_updates"]:
                sections.append(f"• **{update['person']}**: {update['update']}")
            sections.append("")
        
        logger.debug(f"Built {len(sections)} sections: {sections[:3]}...")  # Show first 3 sections
        
        if not sections:
            logger.warning("No sections built - returning 'No significant updates' message")
            return "No significant updates in recent messages."
        
        # Add header
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"📊 **Message Digest** - {timestamp}\n" + "=" * 40 + "\n\n"
        
        result = header + "\n".join(sections)
        logger.debug(f"Final digest text length: {len(result)} characters")
        return result
    
    async def save_digest_json(self, digest_result: DigestResult, file_path: str) -> bool:
        """Save digest as JSON file"""
        try:
            output_data = {
                "digest": digest_result.structured_data,
                "metadata": digest_result.metadata,
                "generated_at": datetime.now().isoformat(),
                "success": digest_result.success
            }
            
            if digest_result.error_message:
                output_data["error"] = digest_result.error_message
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved digest JSON to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save digest JSON: {e}")
            return False