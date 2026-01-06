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

Required AI services:
- Moss (Semantic Retrieval)
- Deepgram (Speech-to-Text)
- OpenAI (LLM)
- Cartesia (Text-to-Speech)
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.run import main as runner_main
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams

from pipecat_moss import MossRetrievalService

# Load environment variables from .env file
load_dotenv(override=True)

print("Starting Customer Support Voice AI Bot...")
logger.debug("All components loaded successfully!")

async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    """Run the customer support bot pipeline."""

    # Initialize stt, tts, llm services
    logger.debug("Starting customer support bot")
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )
    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("OPENAI_MODEL", "gpt-4"),
    )

    # Configure Moss retrieval credentials and settings
    project_id = os.getenv("MOSS_PROJECT_ID")
    project_key = os.getenv("MOSS_PROJECT_KEY")
    index_name = os.getenv("MOSS_INDEX_NAME")
    top_k = int(os.getenv("MOSS_TOP_K", "5"))

    moss_service = MossRetrievalService(
        project_id=project_id,
        project_key=project_key,
        system_prompt="Relevant passages from the Moss knowledge base:\n\n",
    )

    # Load the Moss index
    await moss_service.load_index(index_name)
    logger.debug(f"Moss retrieval service initialized (index: {index_name})")

    # System prompt with semantic retrieval support
    system_content = """You are a helpful customer support voice assistant.
Your role is to assist customers with their questions about orders, shipping,
returns, payments, and general inquiries.

Guidelines:
- Be friendly, professional, and concise in your responses
- Keep responses conversational since this is a voice interface
- Use any provided knowledge base context to give accurate, helpful answers
- If you don't have specific information,
  acknowledge this and offer to connect them with a human agent
- Ask clarifying questions if the customer's request is unclear
- Always prioritize customer satisfaction and be empathetic

When relevant knowledge base information is provided,
use it to give accurate and detailed responses."""

    # Initialize conversation context and pipeline components
    messages = [
        {
            "role": "system",
            "content": system_content,
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)
    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    # Build the processing pipeline with Moss Information injection
    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            rtvi,  # RTVI processor
            stt,  # Speech-to-text
            context_aggregator.user(),  # User responses
            moss_service.query(index_name, top_k=top_k),  # Moss retrieval
            llm,  # LLM (receives enhanced context)
            tts,  # Text-to-speech
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    # Create and configure the pipeline task
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            report_only_initial_ttfb=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    # Define transport event handlers
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.debug("Customer connected to support")
        # Kick off the conversation with a customer support greeting
        greeting = (
            "A customer has just connected to customer support. Greet them warmly and ask how you "
            "can help them today."
        )
        messages.append({"role": "system", "content": greeting})
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.debug("Customer disconnected from support")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=runner_args.handle_sigint)

    await runner.run(task)

# Runner entry point
async def bot(runner_args: RunnerArguments):
    """Main bot entry point for the customer support bot."""
    # Check required environment variables
    required_vars = [
        "DEEPGRAM_API_KEY",
        "CARTESIA_API_KEY",
        "OPENAI_API_KEY",
        "MOSS_PROJECT_ID",
        "MOSS_PROJECT_KEY",
        "MOSS_INDEX_NAME",
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error("Missing required environment variables:")
        for var in missing_vars:
            logger.error(f"   - {var}")
        logger.error("\nPlease update your .env file with the required API keys")
        logger.error("Get your OpenAI API key from: https://platform.openai.com/")
        logger.error("Get your Moss credentials from: https://portal.usemoss.dev")
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
    runner_main()
