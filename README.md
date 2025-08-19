# Simple Telegram Digest Bot

A simplified Telegram bot that monitors channels/chats, processes messages with AI, and sends concise summaries to your Saved Messages.

## Quick Start

1. **Install dependencies** (using the existing virtual environment):
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure the bot**:
   - Edit `config.yaml` with your settings
   - Edit `watchlist.yaml` to specify chats to monitor
   - Your API credentials are already loaded from `.env`

3. **Run the bot**:
   ```bash
   source .venv/bin/activate
   python main.py
   ```

## Features

- 📥 **Collect** - Get recent messages from specified Telegram chats
- 🔍 **Filter** - Keep only messages from the last X hours (client-side)
- 🤖 **Process** - Send filtered messages to OpenAI for AI analysis
- 📄 **Output** - Generate Markdown digest file and send concise summary to Telegram

## File Structure

```
├── main.py           # Entry point and orchestration
├── config.py         # Configuration loading (YAML + .env)
├── telegram.py       # Telegram API interface (Telethon)
├── llm.py           # OpenAI API provider
├── output.py        # Markdown files and Telegram summaries
├── config.yaml      # Bot configuration
├── watchlist.yaml   # Chats to monitor
├── prompt.txt       # System prompt for AI
├── requirements.txt # Dependencies
└── digests/         # Output folder for Markdown files
```

## Configuration

### config.yaml
- **telegram**: API credentials and session settings
- **llm**: OpenAI model and API key  
- **settings**: Hours back to look, output directory

### watchlist.yaml
- **chats**: List of channels/chats to monitor
- Each chat can be enabled/disabled individually
- Use `@username` for public channels, `chat_id` for private chats

## Output

- **Markdown files**: Detailed digest saved to `digests/` folder
- **Telegram summary**: Concise summary sent to your Saved Messages

## Modular Design

Each module can be replaced independently:
- Change **LLM provider** → edit `llm.py` only
- Change **output format** → edit `output.py` only  
- Change **Telegram client** → edit `telegram.py` only
- Change **configuration** → edit `config.py` only

## Example Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Run digest generation once
python main.py

# Show help
python main.py --help
```

The bot will:
1. Load configuration from YAML files and .env
2. Connect to Telegram and collect recent messages
3. Process messages with OpenAI to generate structured digest
4. Save detailed Markdown file to `digests/` folder
5. Send concise summary to your Telegram Saved Messages

## Troubleshooting

- **Authentication**: First run will prompt for phone number and verification code
- **No messages**: Check `watchlist.yaml` chat names and enable status
- **API errors**: Verify OpenAI API key in `.env` file
- **Import errors**: Make sure virtual environment is activated: `source .venv/bin/activate`