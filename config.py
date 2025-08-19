"""
Configuration loader for Telegram Digest Bot
Loads YAML configs and merges with environment variables
"""
import os
import yaml
from typing import Dict, Any
from dotenv import load_dotenv


def load_config() -> Dict[str, Any]:
    """
    Load and validate configuration from YAML files and environment variables
    Priority: .env variables override config.yaml values
    """
    # Load environment variables first
    load_dotenv()
    
    # Load main config
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("config.yaml not found, using default configuration")
        config = {}
    
    # Load watchlist
    try:
        with open('watchlist.yaml', 'r') as f:
            watchlist = yaml.safe_load(f)
    except FileNotFoundError:
        print("watchlist.yaml not found, no chats will be monitored")
        watchlist = {'chats': []}
    
    # Merge environment variables (override config file values)
    if 'telegram' not in config:
        config['telegram'] = {}
    
    if 'llm' not in config:
        config['llm'] = {}
    
    if 'openai' not in config['llm']:
        config['llm']['openai'] = {}
    
    # Telegram config from env vars
    if os.getenv('TELEGRAM_API_ID'):
        config['telegram']['api_id'] = int(os.getenv('TELEGRAM_API_ID'))
    
    if os.getenv('TELEGRAM_API_HASH'):
        config['telegram']['api_hash'] = os.getenv('TELEGRAM_API_HASH')
    
    # OpenAI config from env vars  
    if os.getenv('OPENAI_API_KEY'):
        config['llm']['openai']['api_key'] = os.getenv('OPENAI_API_KEY')
    
    # Set defaults
    if 'session_file' not in config['telegram']:
        config['telegram']['session_file'] = 'bot_session'
    
    if 'provider' not in config['llm']:
        config['llm']['provider'] = 'openai'
    
    if 'model' not in config['llm']['openai']:
        config['llm']['openai']['model'] = 'gpt-4o-mini'
    
    if 'settings' not in config:
        config['settings'] = {}
    
    if 'hours_back' not in config['settings']:
        config['settings']['hours_back'] = 24
    
    if 'output_dir' not in config['settings']:
        config['settings']['output_dir'] = 'digests'
    
    # Add watchlist to config
    config['watchlist'] = watchlist
    
    # Load system prompt
    try:
        with open('prompt.txt', 'r') as f:
            config['prompt'] = f.read().strip()
    except FileNotFoundError:
        print("prompt.txt not found, using default prompt")
        config['prompt'] = """You are a messaging digest assistant. Analyze the messages and extract key information into JSON format with the following structure:
{
  "urgent": [],
  "decisions": [], 
  "topics": [],
  "people_updates": [],
  "calendar": [],
  "unanswered_mentions": []
}"""
    
    # Validate required fields
    _validate_config(config)
    
    return config


def _validate_config(config: Dict[str, Any]) -> None:
    """Validate that required configuration fields are present"""
    required_fields = [
        ('telegram', 'api_id'),
        ('telegram', 'api_hash'),
    ]
    
    for section, field in required_fields:
        if section not in config:
            raise ValueError(f"Missing required config section: {section}")
        if field not in config[section]:
            raise ValueError(f"Missing required config field: {section}.{field}")
    
    # Validate LLM provider config
    provider = config['llm']['provider']
    if provider == 'openai':
        if 'api_key' not in config['llm']['openai']:
            raise ValueError("OpenAI API key is required when using OpenAI provider")
    elif provider == 'ollama':
        if 'ollama' not in config['llm']:
            raise ValueError("Ollama configuration is required when using Ollama provider")
        ollama_config = config['llm']['ollama']
        if 'base_url' not in ollama_config:
            raise ValueError("Ollama base_url is required")
        if 'model' not in ollama_config:
            raise ValueError("Ollama model is required")
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    
    # Validate watchlist
    if 'chats' not in config['watchlist']:
        print("Warning: No chats configured in watchlist")
    
    print(f"Configuration loaded successfully:")
    print(f"  - Telegram API ID: {config['telegram']['api_id']}")
    print(f"  - LLM Provider: {config['llm']['provider']}")
    print(f"  - Hours back: {config['settings']['hours_back']}")
    print(f"  - Chats monitored: {len(config['watchlist'].get('chats', []))}")