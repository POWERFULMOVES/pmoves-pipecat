#!/usr/bin/env python3
"""PMOVES Agent Zero Voice Agent — Pipecat + TensorZero + Ultimate-TTS-Studio.

Full voice agent pipeline:
  Mic -> SileroVAD -> Whisper STT -> TensorZero LLM -> Ultimate-TTS -> Speaker

Components:
  - LocalAudioTransport: Mic input / speaker output
  - SileroVADAnalyzer: Voice activity detection (filters silence)
  - OpenAI STT: Whisper via TensorZero or direct ffmpeg-whisper
  - OpenAI LLM: TensorZero gateway (OpenAI-compatible, routes to local models)
  - UltimateTTSService: Custom service calling TTS Studio Gradio predict API

Usage:
    cd PMOVES-Pipecat
    .venv/Scripts/python examples/pmoves/agent_zero_voice.py

Env vars:
    TENSORZERO_URL  - TensorZero gateway (default: http://localhost:3030)
    TTS_STUDIO_URL  - Ultimate-TTS-Studio (default: http://127.0.0.1:7860)
    TTS_ENGINE      - TTS engine (default: kitten_tts)
    TTS_VOICE       - Voice preset (default: expr-voice-2-f)
"""
import asyncio
import os
import sys

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from ultimate_tts_service import UltimateTTSService

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# --- Configuration ---
TENSORZERO_URL = os.getenv("TENSORZERO_URL", "http://localhost:3030")
TTS_STUDIO_URL = os.getenv("TTS_STUDIO_URL", "http://127.0.0.1:7860")
TTS_ENGINE = os.getenv("TTS_ENGINE", "kitten_tts")
TTS_VOICE = os.getenv("TTS_VOICE", "expr-voice-2-f")

SYSTEM_PROMPT = (
    "You are Agent Zero, the primary orchestrator of the PMOVES.AI platform. "
    "You coordinate autonomous agents, manage knowledge retrieval, and assist "
    "users with research, creative projects, and infrastructure tasks. "
    "Keep responses concise and conversational — you are speaking aloud."
)


async def main():
    """Run the full voice agent pipeline."""
    # Audio I/O via local mic and speakers
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )

    # LLM via TensorZero gateway (OpenAI-compatible)
    llm = OpenAILLMService(
        api_key="not-needed",
        base_url=f"{TENSORZERO_URL}/openai/v1",
        model="tensorzero::agent_zero::qwen3_8b",
    )

    # TTS via Ultimate-TTS-Studio native (Gradio predict API)
    tts = UltimateTTSService(
        base_url=TTS_STUDIO_URL,
        engine=TTS_ENGINE,
        voice=TTS_VOICE,
    )

    # Conversation context with system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    # Pipeline: input -> user context -> LLM -> TTS -> output
    pipeline = Pipeline([
        transport.input(),
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(
        pipeline,
        PipelineParams(allow_interruptions=True),
    )

    @transport.event_handler("on_first_participant_joined")
    async def on_joined(transport, participant):
        await task.queue_frames([
            LLMMessagesFrame(messages),
        ])

    runner = PipelineRunner(handle_sigint=sys.platform != "win32")
    await runner.run(task)


if __name__ == "__main__":
    print("PMOVES Agent Zero Voice Agent")
    print("=" * 40)
    print(f"LLM Backend:  {TENSORZERO_URL}/openai/v1")
    print(f"TTS Backend:  {TTS_STUDIO_URL} (engine={TTS_ENGINE})")
    print(f"TTS Voice:    {TTS_VOICE}")
    print("Starting pipeline... (speak into your microphone)")
    print()
    asyncio.run(main())
