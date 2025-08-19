"""
Output formatting for digest files and Telegram summaries
Creates readable Markdown files and concise Telegram messages
"""
import os
from datetime import datetime
from typing import Dict, Any


def create_markdown_file(digest_data: Dict[str, Any], output_dir: str = "digests") -> str:
    """
    Format digest data as Markdown and save to timestamped file
    Returns the file path
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"digest_{timestamp}.md"
    filepath = os.path.join(output_dir, filename)
    
    # Generate markdown content
    markdown_content = format_as_markdown(digest_data)
    
    # Write to file
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"Markdown digest saved to: {filepath}")
        return filepath
    except Exception as e:
        print(f"Failed to save markdown file: {e}")
        return ""


def format_as_markdown(digest_data: Dict[str, Any]) -> str:
    """Format digest data as readable Markdown"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    content = f"# Telegram Digest - {timestamp}\n\n"
    
    # Count non-empty sections for summary
    sections_with_content = 0
    
    # Urgent Items
    if digest_data.get('urgent'):
        content += "## 🚨 Urgent Items\n"
        for item in digest_data['urgent']:
            content += f"- {item}\n"
        content += "\n"
        sections_with_content += 1
    
    # Unanswered Mentions (high priority)
    if digest_data.get('unanswered_mentions'):
        content += "## ❓ Needs Your Response\n"
        for mention in digest_data['unanswered_mentions']:
            content += f"- {mention}\n"
        content += "\n"
        sections_with_content += 1
    
    # Calendar Events
    if digest_data.get('calendar'):
        content += "## 📅 Calendar Events\n"
        for event in digest_data['calendar']:
            time_str = f" at {event['time']}" if event.get('time') else ""
            content += f"- {event['event']} - {event['date']}{time_str}\n"
        content += "\n"
        sections_with_content += 1
    
    # Decisions Made
    if digest_data.get('decisions'):
        content += "## ✅ Decisions Made\n"
        for decision in digest_data['decisions']:
            content += f"- {decision}\n"
        content += "\n"
        sections_with_content += 1
    
    # Topics Discussed
    if digest_data.get('topics'):
        content += "## 💬 Topics Discussed\n"
        for topic in digest_data['topics']:
            content += f"### {topic['topic']}\n"
            if topic.get('participants'):
                participants = ', '.join(topic['participants'])
                content += f"*Participants: {participants}*\n"
            content += f"{topic['summary']}\n\n"
        sections_with_content += 1
    
    # People Updates
    if digest_data.get('people_updates'):
        content += "## 👥 People Updates\n"
        for update in digest_data['people_updates']:
            content += f"- **{update['person']}**: {update['update']}\n"
        content += "\n"
        sections_with_content += 1
    
    # Add footer if no content
    if sections_with_content == 0:
        content += "## 💤 No Activity\n\nNo significant messages found in the monitored chats.\n"
    
    return content


def format_telegram_summary(digest_data: Dict[str, Any]) -> str:
    """
    Create concise text for Telegram (max 2-3 lines per section)
    Focus on urgent/actionable items only
    """
    lines = []
    
    # Count items for header
    urgent_count = len(digest_data.get('urgent', []))
    decisions_count = len(digest_data.get('decisions', []))
    mentions_count = len(digest_data.get('unanswered_mentions', []))
    calendar_count = len(digest_data.get('calendar', []))
    
    # Header with counts
    summary_parts = []
    if urgent_count > 0:
        summary_parts.append(f"{urgent_count} urgent")
    if decisions_count > 0:
        summary_parts.append(f"{decisions_count} decisions")
    if mentions_count > 0:
        summary_parts.append(f"{mentions_count} needs response")
    if calendar_count > 0:
        summary_parts.append(f"{calendar_count} calendar")
    
    if summary_parts:
        lines.append(f"🔔 Digest: {', '.join(summary_parts)}")
    else:
        lines.append("🔔 Digest: No significant activity")
        return '\n'.join(lines)
    
    # Urgent items (top 2 only)
    if digest_data.get('urgent'):
        urgent_items = digest_data['urgent'][:2]  # Limit to 2 most urgent
        for item in urgent_items:
            # Truncate long items
            item_text = item[:80] + "..." if len(item) > 80 else item
            lines.append(f"🚨 {item_text}")
        if len(digest_data['urgent']) > 2:
            lines.append(f"🚨 +{len(digest_data['urgent']) - 2} more urgent items")
    
    # Unanswered mentions (top 2 only)  
    if digest_data.get('unanswered_mentions'):
        mentions = digest_data['unanswered_mentions'][:2]
        for mention in mentions:
            mention_text = mention[:80] + "..." if len(mention) > 80 else mention
            lines.append(f"❓ {mention_text}")
        if len(digest_data['unanswered_mentions']) > 2:
            lines.append(f"❓ +{len(digest_data['unanswered_mentions']) - 2} more mentions")
    
    # Next calendar event only
    if digest_data.get('calendar'):
        next_event = digest_data['calendar'][0]  # Assuming sorted by date
        time_str = f" at {next_event['time']}" if next_event.get('time') else ""
        lines.append(f"📅 Next: {next_event['event']} - {next_event['date']}{time_str}")
    
    # Key decisions (top 1 only)
    if digest_data.get('decisions'):
        decision = digest_data['decisions'][0]
        decision_text = decision[:80] + "..." if len(decision) > 80 else decision
        lines.append(f"✅ {decision_text}")
        if len(digest_data['decisions']) > 1:
            lines.append(f"✅ +{len(digest_data['decisions']) - 1} more decisions")
    
    return '\n'.join(lines)