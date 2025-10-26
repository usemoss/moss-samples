"""Configuration settings for the LiveKit Voice Agent.

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
    """Moss FAQ index configuration."""
    index_name: str = "TalkToPdf-index-livekit"
    model_id: str = "moss-minilm"
    top_k_results: int = 6

@dataclass
class UnSiloedConfig:
    data_path: str = "Yatharth-Kapadia-Resume-ALL.pdf"
    max_tokens_per_chunk: int = 100  # Token limit for each chunk
    overlap_tokens: int = 25  # Number of tokens to overlap between chunks


@dataclass
class AgentConfig:
    """Main agent configuration combining all sub-configs."""
    stt: STTConfig = field(default_factory=STTConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    moss: MossConfig = field(default_factory=MossConfig)
    unsiloed: UnSiloedConfig = field(default_factory=UnSiloedConfig)
    
    # Agent behavior settings
    instructions: str = """You are a warm, professional customer support agent for our ecommerce help desk.
            Before responding to any user, always call the `search_support_faqs` tool to gather
            the most relevant articles from the Moss-powered FAQ index. Use that material to craft grounded, step-by-step assistance,
            quote key policies when helpful, and acknowledge when information is unavailable.
            Keep responses concise, empathetic, and action-oriented, and invite follow-up
            questions when appropriate."""
    
    initial_greeting_instructions: str = "Greet the user warmly and ask how you can help."


# Global settings instance
settings = AgentConfig()


def get_settings() -> AgentConfig:
    """Get the global settings instance."""
    return settings

