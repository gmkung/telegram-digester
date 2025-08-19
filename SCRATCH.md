# Simple Telegram Digest Bot - Rebuild Instructions

## Project Goal
Build a simplified Telegram bot that monitors channels/chats, processes messages with AI, and sends concise summaries to your Saved Messages.


## Core Workflow
1. **Collect** - Get recent messages from specified Telegram chats
2. **Filter** - Keep only messages from the last X hours (client-side)
3. **Process** - Send filtered messages to OpenAI or Ollama for analysis
4. **Output** - Generate Markdown digest file and send concise summary to Telegram

## Modular Architecture

### Module 1: Configuration (`config.py`)
**Purpose**: Load and validate settings
**Input**: YAML config files
**Output**: Configuration dictionaries
```python
def load_config() -> dict:
    # Load config.yaml and watchlist.yaml
    # Validate required fields
    # Return merged config
```

### Module 2: Telegram Client (`telegram.py`)
**Purpose**: Interface with Telegram API
**Dependencies**: telethon
```python
async def collect_messages(watchlist, hours_back) -> List[dict]:
    # Connect to Telegram
    # For each chat in watchlist:
    #   - Fetch recent messages
    #   - Filter by timestamp (client-side)
    # Return normalized message list

async def send_summary(text: str):
    # Send concise text to Saved Messages
```

### Module 3: LLM Provider (`llm.py`)
**Purpose**: Generate digest using AI
**Choose ONE**: OpenAI Responses API OR Ollama
```python
async def generate_digest(messages: List[dict], prompt: str) -> dict:
    # Format messages for LLM
    # Call OpenAI or Ollama API
    # Parse JSON response
    # Return structured digest
```

### Module 4: Output Generator (`output.py`)  
**Purpose**: Format and save results
```python
def create_markdown_file(digest_data: dict) -> str:
    # Format digest as readable Markdown
    # Save to timestamped file
    # Return file path

def format_telegram_summary(digest_data: dict) -> str:
    # Create concise text for Telegram (max 2-3 lines per section)
    # Focus on urgent/actionable items only
```

### Module 5: Main Runner (`main.py`)
**Purpose**: Orchestrate all modules
```python
async def main():
    config = load_config()
    messages = await collect_messages(config['watchlist'], config['hours_back'])
    if messages:
        digest = await generate_digest(messages, config['prompt'])
        markdown_file = create_markdown_file(digest)
        summary = format_telegram_summary(digest)
        await send_summary(summary)
```

## File Structure
```
simple-digest-bot/
├── main.py           # Entry point and orchestration
├── config.py         # Configuration loading
├── telegram.py       # Telegram API interface  
├── llm.py           # LLM provider (OpenAI OR Ollama)
├── output.py        # Markdown and summary formatting
├── config.yaml      # Bot configuration
├── watchlist.yaml   # Chats to monitor
├── prompt.txt       # System prompt for AI
├── requirements.txt # Dependencies
└── digests/         # Output folder for Markdown files
```

## API Reference

### OpenAI Responses API
```python
response = client.responses.parse(
    model="gpt-4o-mini",
    input=f"{system_prompt}\n\n{messages_text}",
    text_format=DigestStructure  # Pydantic model
)
result = response.output_parsed.model_dump()
```

### Ollama Chat API  
```python
response = await httpx_client.post("http://localhost:11434/api/chat", json={
    "model": "mistral:latest",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": messages_text}
    ],
    "format": "json",
    "stream": false
})
result = json.loads(response.json()["message"]["content"])
```

### Expected JSON Schema
```json
{
  "urgent": ["High priority items"],
  "decisions": ["Decisions made"],
  "topics": [{"topic": "Topic name", "summary": "Brief summary", "participants": ["names"]}],
  "people_updates": [{"person": "Name", "update": "What happened"}],
  "calendar": [{"event": "Event name", "date": "2024-01-01", "time": "14:00"}],
  "unanswered_mentions": ["Questions directed at you"]
}
```

### Telegram Message Format
```python
async for message in client.iter_messages(chat, limit=500):
    if message.date >= cutoff_time:  # Client-side filtering
        messages.append({
            'chat': chat_name,
            'sender': sender_name, 
            'time': message.date,
            'text': message.text
        })
```

## Output Formats

### Markdown Digest File
```markdown
# Telegram Digest - 2024-01-15 14:30

## 🚨 Urgent Items
- Server outage reported in #alerts
- Contract review needed by Friday

## ✅ Decisions Made  
- Budget approved for Q1 marketing

## 💬 Topics Discussed
### Project Alpha Launch
*Participants: Alice, Bob, Carol*
Discussion about timeline and resource allocation for the new product launch.

## 👥 People Updates
- **Alice**: Started maternity leave, will be back in March
- **Bob**: Promoted to Senior Developer

## 📅 Calendar Events
- Team standup - January 16, 2024 at 09:00
- Project deadline - January 20, 2024

## ❓ Needs Your Response
- @alice asked about the budget approval process
- Review the proposal shared in #general
```

### Telegram Summary (Concise)
```
🔔 Digest: 3 urgent items, 2 decisions, 1 needs response
🚨 Server outage in #alerts, contract review due Friday
❓ @alice waiting for budget approval process info
📅 Next: Team standup tomorrow 9am
```

## Configuration Files

### config.yaml
```yaml
telegram:
  api_id: 12345
  api_hash: "your_hash"
  session_file: "bot_session"

llm:
  provider: "openai"  # or "ollama"
  openai:
    model: "gpt-4o-mini"
    api_key: "your_key"
  ollama:
    base_url: "http://localhost:11434"  
    model: "mistral:latest"

settings:
  hours_back: 24
  output_dir: "digests"
```

### watchlist.yaml
```yaml
chats:
  - name: "@channel_name"
    enabled: true
  - name: "Private Group"  
    chat_id: -1001234567890
    enabled: true
```

## Implementation Notes

### Overengineered Parts to Avoid
- ❌ Complex storage/cursor tracking systems
- ❌ Multi-provider abstraction layers
- ❌ Hot configuration reloading
- ❌ Detailed logging with request IDs
- ❌ Pydantic validation (use basic dict checks)
- ❌ Message priority scoring algorithms

### Keep Simple
- ✅ Basic time-based filtering only
- ✅ Choose ONE LLM provider at config time
- ✅ Static configuration (restart to change settings)
- ✅ Simple logging with print statements
- ✅ Direct dictionary manipulation
- ✅ File-based output (no databases)

### Error Handling
- Fail fast with clear error messages
- Log API responses for debugging
- Continue processing even if one chat fails
- Graceful degradation (skip broken configs)

This modular design allows you to:
- Replace any single file without affecting others
- Test each module independently  
- Add new LLM providers by only changing `llm.py`
- Modify output formats by only changing `output.py`
- Switch Telegram libraries by only changing `telegram.py`