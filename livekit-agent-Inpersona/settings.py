"""Configuration settings for the LiveKit Voice Agent - Inpersona.

This module centralizes all model and service configurations,
making it easy to adjust voice pipeline settings without modifying code.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class STTConfig:
    """Speech-to-Text configuration."""
    provider: str = "deepgram"
    model: str = "nova-2"
    language: str = "en"


@dataclass
class LLMConfig:
    """Large Language Model configuration."""
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: Optional[int] = None


@dataclass
class TTSConfig:
    """Text-to-Speech configuration."""
    provider: str = "cartesia"
    model: str = "sonic-2"
    voice: str = "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Default voice ID
    speed: float = 1.0


@dataclass
class VADConfig:
    """Voice Activity Detection configuration."""
    provider: str = "silero"


@dataclass
class MossConfig:
    """Moss index configuration for life details."""
    index_name: str = "Inpersona-index-livekit"  # Change this to match your existing index name
    model_id: str = "moss-minilm"
    top_k_results: int = 6
    data_path: str = "life.json"


@dataclass
class AgentConfig:
    """Main agent configuration combining all sub-configs."""
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    moss: MossConfig = field(default_factory=MossConfig)
    
    # Agent behavior settings
    instructions: str = """You are an AI assistant that impersonates a person based on the details in a JSON file.
            Your first task is to identify the person's name from the context you receive from the `search_life_details` tool.
            Once you know the name, you must act as if you are that person.
            All your knowledge about this person comes from the JSON file.
            Before responding to any user, always call the `search_life_details` tool to find relevant information and use that to construct your answer.
            Always speak in the first person as the person you are impersonating. Be conversational and natural."""
    
    initial_greeting_instructions: str = "Greet the user warmly and ask how you can help."


# Global settings instance
settings = AgentConfig()


def get_settings() -> AgentConfig:
    """Get the global settings instance."""
    return settings

