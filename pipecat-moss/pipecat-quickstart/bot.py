#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipecat Customer Support Voice AI Bot with Moss Semantic Retrieval.

A voice AI customer support assistant that:
- Uses OpenAI for intelligent responses
- Searches knowledge base using Moss semantic retrieval
- Supports real-time voice conversations
- Follows official Pipecat quickstart pattern

Required AI services:
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)

Run the bot using::

    uv run bot.py
"""

import os
import sys

from dotenv import load_dotenv
from loguru import logger
from pipecat.frames.frames import LLMRunFrame

print("Starting Customer Support Voice AI Bot...")
print("Loading models and imports (20 seconds first run only)\n")

logger.info("Loading Silero VAD model...")
from pipecat.audio.vad.silero import SileroVADAnalyzer

logger.info("Silero VAD model loaded")
logger.info("Loading pipeline components...")
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
# Import Moss retrieval service
from client import MossClient
from retrieval import MossRetrievalService

logger.info("All components loaded successfully!")

# Add project root to path for our imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


load_dotenv(override=True)


def create_llm_service():
    """Create LLM service with Azure OpenAI or regular OpenAI support.

    Returns:
        An instance of OpenAILLMService configured for either Azure or standard OpenAI.
    """
    # Check for Azure OpenAI configuration
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY") 
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    
    if azure_endpoint and azure_api_key and azure_deployment:
        logger.info("Using Azure OpenAI configuration")
        azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
        
        # Construct Azure OpenAI base URL
        base_url = f"{azure_endpoint.rstrip('/')}/openai/deployments/{azure_deployment}"
        
        return OpenAILLMService(
            api_key=azure_api_key,
            base_url=base_url,
            model=azure_deployment,
            default_headers={
                "api-version": azure_api_version
            }
        )
    else:
        logger.info("Using standard OpenAI configuration")
        
        # Get configuration for OpenAI (supports custom base_url and model)
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")  # Optional custom endpoint
        model = os.getenv("OPENAI_MODEL", "gpt-4")  # Default to gpt-4 if not specified
        
        if base_url:
            logger.info(f"Using custom OpenAI endpoint: {base_url}")
            return OpenAILLMService(
                api_key=api_key,
                base_url=base_url,
                model=model
            )
        else:
            return OpenAILLMService(
                api_key=api_key,
                model=model
            )


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Run the customer support bot pipeline.

    Args:
        transport: The transport layer to use (e.g., Daily, WebRTC).
        runner_args: Arguments for the pipeline runner.
    """
    logger.info(f"Starting customer support bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    llm = create_llm_service()

    # Moss Retrieval Setup
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")

    if not project_id or not project_key:
        raise RuntimeError(
            "Missing Moss credentials. Please set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in your environment."
        )

    try:
        moss_client = MossClient(project_id=project_id, project_key=project_key)
    except (RuntimeError, ValueError) as exc:
        raise RuntimeError(
            "Unable to initialize MossClient. "
            "Ensure `inferedge-moss` is installed and Moss credentials are set."
        ) from exc

    # Configure defaults if not set
    index_name = os.getenv("MOSS_INDEX_NAME", "faq-index-livekit")
    top_k = int(os.getenv("MOSS_TOP_K", "3"))

    moss_retrieval = MossRetrievalService(
        index_name=index_name,
        top_k=top_k,
        system_prompt="Relevant passages from the Moss knowledge base:\n\n",
        add_as_system_message=True,
        deduplicate_queries=True,
        max_documents=top_k,
        client=moss_client,
    )
    logger.info(f"Moss retrieval service initialized (index: {index_name})")

    # System prompt with semantic retrieval support
    system_content = """You are a helpful customer support voice assistant. Your role is to assist customers with their questions about orders, shipping, returns, payments, and general inquiries.

Guidelines:
- Be friendly, professional, and concise in your responses
- Keep responses conversational since this is a voice interface
- Use any provided knowledge base context to give accurate, helpful answers
- If you don't have specific information, acknowledge this and offer to connect them with a human agent
- Ask clarifying questions if the customer's request is unclear
- Always prioritize customer satisfaction and be empathetic

When relevant knowledge base information is provided, use it to give accurate and detailed responses."""

    messages = [
        {
            "role": "system",
            "content": system_content,
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))
    
    pipeline = Pipeline([
        transport.input(),  # Transport user input
        rtvi,  # RTVI processor  
        stt,  # Speech-to-text
        context_aggregator.user(),  # User responses
        moss_retrieval,  # Moss retrieval (intercepts LLM messages)
        llm,  # LLM (receives enhanced context)
        tts,  # Text-to-speech
        transport.output(),  # Transport bot output
        context_aggregator.assistant(),  # Assistant spoken responses
    ])

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            report_only_initial_ttfb=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Customer connected to support")
        # Kick off the conversation with a customer support greeting
        greeting = "A customer has just connected to customer support. Greet them warmly and ask how you can help them today."
        messages.append({"role": "system", "content": greeting})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Customer disconnected from support")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    """Main bot entry point for the customer support bot.

    Args:
        runner_args: Command line arguments parsed by the runner.
    """

    # Check required environment variables
    required_vars = ["DEEPGRAM_API_KEY", "CARTESIA_API_KEY", "OPENAI_API_KEY"]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error("Missing required environment variables:")
        for var in missing_vars:
            logger.error(f"   - {var}")
        logger.error("\nPlease update your .env file with the required API keys")
        logger.error("Get your OpenAI API key from: https://platform.openai.com/")
        return

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()