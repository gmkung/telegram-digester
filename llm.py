"""
LLM provider for digest generation
Supports OpenAI Responses API and Ollama Chat API with basic dict validation (no Pydantic)
"""
import json
import time
from typing import Dict, Any, List
from openai import OpenAI
import httpx


class DigestStructure:
    """Simple validation structure without Pydantic"""
    @staticmethod
    def validate(data: Dict[str, Any]) -> Dict[str, Any]:
        """Basic validation and default filling for digest structure"""
        validated = {
            'urgent': [],
            'decisions': [],
            'topics': [],
            'people_updates': [],
            'calendar': [],
            'unanswered_mentions': []
        }
        
        if not isinstance(data, dict):
            print("Warning: LLM returned non-dict response, using empty structure")
            return validated
        
        # Validate and copy each field
        for field in validated.keys():
            if field in data:
                if field in ['urgent', 'decisions', 'unanswered_mentions']:
                    # These should be lists of strings
                    if isinstance(data[field], list):
                        validated[field] = [str(item) for item in data[field]]
                    else:
                        print(f"Warning: {field} should be a list, got {type(data[field])}")
                
                elif field == 'topics':
                    # List of topic objects
                    if isinstance(data[field], list):
                        topics = []
                        for topic in data[field]:
                            if isinstance(topic, dict):
                                topics.append({
                                    'topic': str(topic.get('topic', '')),
                                    'summary': str(topic.get('summary', '')),
                                    'participants': [str(p) for p in topic.get('participants', [])]
                                })
                        validated[field] = topics
                    else:
                        print(f"Warning: {field} should be a list, got {type(data[field])}")
                
                elif field == 'people_updates':
                    # List of people update objects
                    if isinstance(data[field], list):
                        updates = []
                        for update in data[field]:
                            if isinstance(update, dict):
                                updates.append({
                                    'person': str(update.get('person', '')),
                                    'update': str(update.get('update', ''))
                                })
                        validated[field] = updates
                    else:
                        print(f"Warning: {field} should be a list, got {type(data[field])}")
                
                elif field == 'calendar':
                    # List of calendar event objects
                    if isinstance(data[field], list):
                        events = []
                        for event in data[field]:
                            if isinstance(event, dict):
                                events.append({
                                    'event': str(event.get('event', '')),
                                    'date': str(event.get('date', '')),
                                    'time': str(event.get('time', '')) if event.get('time') else None
                                })
                        validated[field] = events
                    else:
                        print(f"Warning: {field} should be a list, got {type(data[field])}")
        
        return validated


def format_messages_for_llm(messages: List[Dict[str, Any]]) -> str:
    """Format collected messages into text for LLM processing"""
    if not messages:
        return "No messages to process."
    
    # Group messages by chat for better organization
    messages_by_chat = {}
    for msg in messages:
        chat_name = msg['chat']
        if chat_name not in messages_by_chat:
            messages_by_chat[chat_name] = []
        messages_by_chat[chat_name].append(msg)
    
    formatted_text = ""
    
    for chat_name, chat_messages in messages_by_chat.items():
        formatted_text += f"\n## {chat_name} ({len(chat_messages)} messages)\n"
        
        # Sort messages by timestamp within each chat
        chat_messages.sort(key=lambda x: x['time'])
        
        # Add time range info
        if chat_messages:
            start_time = chat_messages[0]['time'].strftime("%H:%M")
            end_time = chat_messages[-1]['time'].strftime("%H:%M")
            date = chat_messages[0]['time'].strftime("%Y-%m-%d")
            formatted_text += f"Time range: {date} {start_time} - {end_time}\n\n"
        
        # Add messages
        for msg in chat_messages:
            timestamp = msg['time'].strftime("%H:%M")
            formatted_text += f"[{timestamp}] {msg['sender']}: {msg['text']}\n"
        
        formatted_text += "\n"
    
    # Add summary statistics
    total_messages = len(messages)
    stats = f"""Message Statistics:
- Total messages: {total_messages}
- Chats involved: {len(messages_by_chat)}

Messages:
"""
    
    return stats + formatted_text


async def generate_digest(messages: List[Dict[str, Any]], prompt: str, llm_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate digest using configured LLM provider (OpenAI or Ollama)
    Returns validated digest structure
    """
    if not messages:
        print("No messages to process")
        return DigestStructure.validate({})
    
    provider = llm_config.get('provider', 'openai').lower()
    
    # Format messages for LLM
    messages_text = format_messages_for_llm(messages)
    
    if provider == 'openai':
        return await _generate_with_openai(messages_text, prompt, llm_config.get('openai', {}))
    elif provider == 'ollama':
        return await _generate_with_ollama(messages_text, prompt, llm_config.get('ollama', {}))
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


async def _generate_with_openai(messages_text: str, prompt: str, openai_config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate digest using OpenAI API"""
    request_id = f"openai_{int(time.time())}"
    
    # Prepare OpenAI client
    client = OpenAI(api_key=openai_config.get('api_key'))
    model = openai_config.get('model', 'gpt-4o-mini')
    
    # Prepare input text
    input_text = f"""{prompt}

{messages_text}

Please analyze these messages and respond with valid JSON matching the required schema."""
    
    try:
        print(f"[{request_id}] Sending messages to OpenAI model {model}")
        
        start_time = time.time()
        
        # Make API call using regular chat completion
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": input_text}
            ],
            response_format={"type": "json_object"}
        )
        
        processing_time = time.time() - start_time
        print(f"[{request_id}] OpenAI response received in {processing_time:.2f} seconds")
        
        # Extract response content
        content = response.choices[0].message.content
        
        # Parse JSON response
        try:
            raw_data = json.loads(content)
            validated_data = DigestStructure.validate(raw_data)
            print(f"[{request_id}] Successfully parsed OpenAI response")
            return validated_data
        except json.JSONDecodeError as e:
            print(f"[{request_id}] Failed to parse JSON response: {e}")
            return DigestStructure.validate({})
    
    except Exception as e:
        print(f"[{request_id}] Error calling OpenAI API: {e}")
        return DigestStructure.validate({})


async def _generate_with_ollama(messages_text: str, prompt: str, ollama_config: Dict[str, Any]) -> Dict[str, Any]:
    """Generate digest using Ollama local API"""
    request_id = f"ollama_{int(time.time())}"
    
    base_url = ollama_config.get('base_url', 'http://localhost:11434')
    model = ollama_config.get('model', 'mistral:latest')
    temperature = ollama_config.get('temperature', 0.3)
    top_p = ollama_config.get('top_p', 0.9)
    
    # Prepare request data
    request_data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": prompt
            },
            {
                "role": "user", 
                "content": messages_text
            }
        ],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p
        }
    }
    
    try:
        print(f"[{request_id}] Sending messages to Ollama model {model}")
        print(f"[{request_id}] System prompt preview: {request_data['messages'][0]['content'][:200]}...")
        print(f"[{request_id}] User messages preview: {request_data['messages'][1]['content'][:500]}...")
        
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=300) as client:  # 5 minute timeout
            response = await client.post(
                f"{base_url}/api/chat",
                json=request_data
            )
            response.raise_for_status()
            
            processing_time = time.time() - start_time
            print(f"[{request_id}] Ollama response received in {processing_time:.2f} seconds")
            
            response_data = response.json()
            
            # Log the full response structure first
            print(f"[{request_id}] Full Ollama response structure:")
            print("=" * 60)
            print(f"Response keys: {list(response_data.keys())}")
            if 'message' in response_data:
                print(f"Message keys: {list(response_data['message'].keys())}")
            print("=" * 60)
            
            content = response_data.get('message', {}).get('content', '')
            
            # Log performance metrics if available
            if 'eval_duration' in response_data:
                eval_time = response_data['eval_duration'] / 1e9  # Convert to seconds
                print(f"[{request_id}] Model evaluation time: {eval_time:.2f} seconds")
            
            # Log the extracted content
            print(f"[{request_id}] Extracted content from response:")
            print("=" * 60)
            print(content)
            print("=" * 60)
            
            # Parse JSON response
            try:
                raw_data = json.loads(content)
                validated_data = DigestStructure.validate(raw_data)
                print(f"[{request_id}] Successfully parsed Ollama response")
                return validated_data
            except json.JSONDecodeError as e:
                print(f"[{request_id}] Failed to parse JSON response: {e}")
                print(f"[{request_id}] Raw content: {content[:500]}...")
                return DigestStructure.validate({})
    
    except httpx.HTTPError as e:
        print(f"[{request_id}] HTTP error calling Ollama API: {e}")
        return DigestStructure.validate({})
    except Exception as e:
        print(f"[{request_id}] Error calling Ollama API: {e}")
        return DigestStructure.validate({})