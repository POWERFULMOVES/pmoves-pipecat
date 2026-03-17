#!/usr/bin/env python3
"""PMOVES Agent Zero Voice Agent — Pipecat + TensorZero + Ultimate-TTS-Studio.

Two modes of operation:

  standalone (default):
    Mic -> SileroVAD -> TensorZero LLM -> Ultimate-TTS -> Speaker
    Runs locally with no Docker dependencies (just TTS Studio + TensorZero).

  flute:
    Connects to Flute-Gateway WebSocket at ws://localhost:8056.
    Uses Flute's built-in pipeline: VAD -> Whisper STT -> TensorZero LLM
    -> VibeVoice TTS -> Speaker (+ optional Google Cast output).
    Requires Flute-Gateway running (docker compose --profile media up -d).

Usage:
    cd PMOVES-Pipecat

    # Standalone mode (local mic/speaker, TTS Studio direct)
    .venv/Scripts/python examples/pmoves/agent_zero_voice.py

    # Flute mode (WebSocket to Flute-Gateway)
    .venv/Scripts/python examples/pmoves/agent_zero_voice.py --mode flute

Env vars:
    TENSORZERO_URL  - TensorZero gateway (default: http://localhost:3030)
    TTS_STUDIO_URL  - Ultimate-TTS-Studio (default: http://127.0.0.1:7860)
    TTS_ENGINE      - TTS engine (default: kitten_tts)
    TTS_VOICE       - Voice preset (default: expr-voice-2-f)
    FLUTE_WS_URL    - Flute-Gateway WebSocket (default: ws://localhost:8056)
"""
import argparse
import asyncio
import json
import os
import sys

from loguru import logger

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

# --- Configuration ---
TENSORZERO_URL = os.getenv("TENSORZERO_URL", "http://localhost:3030")
TTS_STUDIO_URL = os.getenv("TTS_STUDIO_URL", "http://127.0.0.1:7860")
TTS_ENGINE = os.getenv("TTS_ENGINE", "kitten_tts")
TTS_VOICE = os.getenv("TTS_VOICE", "expr-voice-2-f")
FLUTE_WS_URL = os.getenv("FLUTE_WS_URL", "ws://localhost:8056")

SYSTEM_PROMPT = (
    "You are Agent Zero, the primary orchestrator of the PMOVES.AI platform. "
    "You coordinate autonomous agents, manage knowledge retrieval, and assist "
    "users with research, creative projects, and infrastructure tasks. "
    "Keep responses concise and conversational — you are speaking aloud."
)


async def run_standalone():
    """Run standalone voice agent with local mic/speaker + TTS Studio."""
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import LLMMessagesFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.transports.local.audio import (
        LocalAudioTransport,
        LocalAudioTransportParams,
    )

    from ultimate_tts_service import UltimateTTSService

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        )
    )

    llm = OpenAILLMService(
        api_key="not-needed",
        base_url=f"{TENSORZERO_URL}/openai/v1",
        model="tensorzero::agent_zero::qwen3_8b",
    )

    tts = UltimateTTSService(
        base_url=TTS_STUDIO_URL,
        engine=TTS_ENGINE,
        voice=TTS_VOICE,
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

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
        await task.queue_frames([LLMMessagesFrame(messages)])

    runner = PipelineRunner(handle_sigint=sys.platform != "win32")
    await runner.run(task)


async def run_flute():
    """Run voice agent via Flute-Gateway WebSocket.

    Connects to Flute-Gateway's /v1/voice/stream/duplex endpoint which
    provides the full pipeline: VAD -> Whisper STT -> TensorZero LLM ->
    VibeVoice TTS -> audio output (+ optional Google Cast).

    Protocol:
        Send: binary PCM16 audio frames (24kHz, mono)
        Send: {"type": "start", "persona": "assistant"}
        Recv: binary PCM16 audio frames (TTS output)
        Recv: {"type": "transcription", "text": "..."}
    """
    try:
        import websockets
    except ImportError:
        print("ERROR: 'websockets' package required for flute mode.")
        print("Install: pip install websockets")
        sys.exit(1)

    url = f"{FLUTE_WS_URL}/v1/voice/stream/duplex"
    print(f"Connecting to Flute-Gateway: {url}")

    try:
        async with websockets.connect(url) as ws:
            # Start conversation
            await ws.send(json.dumps({
                "type": "start",
                "persona": "assistant",
                "voice": TTS_VOICE,
            }))
            print("Connected. Flute-Gateway handles VAD + STT + LLM + TTS.")
            print("Send audio via another client, or type text below.")
            print("(This demo listens for server messages)")
            print()

            async for message in ws:
                if isinstance(message, bytes):
                    # Audio frame from TTS — in a real client, play it
                    logger.debug("Received %d bytes audio", len(message))
                else:
                    data = json.loads(message)
                    msg_type = data.get("type", "")
                    if msg_type == "transcription":
                        print(f"[STT] {data.get('text', '')}")
                    elif msg_type == "llm_text":
                        print(f"[LLM] {data.get('text', '')}", end="", flush=True)
                    elif msg_type == "response_start":
                        print("\n[Agent speaking...]")
                    elif msg_type == "response_end":
                        print("[Agent done]")
                    elif msg_type == "error":
                        print(f"[ERROR] {data.get('message', '')}")
                    else:
                        logger.debug("Server: %s", data)

    except ConnectionRefusedError:
        print(f"ERROR: Cannot connect to {url}")
        print("Is Flute-Gateway running? Try:")
        print("  docker compose --profile media up -d")
        print("  # or via Pinokio: Start Voice (TTS + Flute + Cast)")
        sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="PMOVES Agent Zero Voice Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Modes:
  standalone  Local mic/speaker + TTS Studio (Gradio predict API)
  flute       WebSocket to Flute-Gateway (full server-side pipeline)

Examples:
  %(prog)s                      # standalone mode (default)
  %(prog)s --mode flute         # connect to Flute-Gateway
  TTS_ENGINE=f5_tts %(prog)s    # use F5-TTS engine
""",
    )
    parser.add_argument(
        "--mode",
        choices=["standalone", "flute"],
        default="standalone",
        help="Pipeline mode (default: standalone)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    print("PMOVES Agent Zero Voice Agent")
    print("=" * 40)
    print(f"Mode:         {args.mode}")

    if args.mode == "standalone":
        print(f"LLM Backend:  {TENSORZERO_URL}/openai/v1")
        print(f"TTS Backend:  {TTS_STUDIO_URL} (engine={TTS_ENGINE})")
        print(f"TTS Voice:    {TTS_VOICE}")
        print("Starting pipeline... (speak into your microphone)")
        print()
        asyncio.run(run_standalone())
    else:
        print(f"Flute WS:     {FLUTE_WS_URL}")
        print(f"Voice:        {TTS_VOICE}")
        print()
        asyncio.run(run_flute())
