"""Pipecat TTSService wrapping Ultimate-TTS-Studio's Gradio predict API.

Uses the synchronous /api/generate_unified_tts endpoint which returns
audio directly without SSE/WebSocket event polling.

Engines: KittenTTS, F5-TTS, Fish Speech S2 Pro, IndexTTS2, VoxCPM,
         Chatterbox Turbo, Higgs Audio, Kokoro, Qwen3 TTS, VibeVoice
"""

import io
import wave
from typing import AsyncGenerator, Optional

import httpx
from loguru import logger

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    StartFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.ai_services import TTSService

# Engine name mapping (Pipecat internal -> Gradio API display name)
ENGINE_NAMES = {
    "kitten_tts": "KittenTTS",
    "kokoro": "Kokoro TTS",
    "f5_tts": "F5-TTS",
    "indextts2": "IndexTTS2",
    "fish": "Fish Speech",
    "chatterbox": "ChatterboxTTS",
    "voxcpm": "VoxCPM",
    "higgs": "Higgs Audio",
    "qwen3_tts": "Qwen3 TTS",
    "vibevoice": "VibeVoice",
}


class UltimateTTSService(TTSService):
    """Pipecat TTS service backed by Ultimate-TTS-Studio.

    Calls the Gradio predict API at /api/generate_unified_tts which
    returns audio synchronously (no WebSocket/SSE needed).
    """

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:7860",
        engine: str = "kitten_tts",
        voice: Optional[str] = None,
        timeout: float = 120.0,
        sample_rate: int = 24000,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._base_url = base_url.rstrip("/")
        self._predict_url = f"{self._base_url}/api"
        self._engine = engine
        self._voice = voice or "expr-voice-2-f"
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._client = httpx.AsyncClient(timeout=self._timeout)
        logger.info(
            "UltimateTTSService started (engine=%s, url=%s)",
            self._engine, self._base_url,
        )

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        if self._client:
            await self._client.aclose()
            self._client = None

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_params(self, text: str) -> list:
        """Build the 92-parameter list for generate_unified_tts."""
        api_engine = ENGINE_NAMES.get(self._engine, self._engine)
        data: list = [None] * 92

        # Core params
        data[0] = text
        data[1] = api_engine
        data[2] = "wav"

        # Chatterbox params (3-8)
        data[4] = 0.5
        data[5] = 0.8
        data[6] = 0.5
        data[7] = 300
        data[8] = 0

        # Chatterbox MTL params (9-18)
        data[10] = "en"
        data[11] = 0.5
        data[12] = 0.8
        data[13] = 0.5
        data[14] = 2.0
        data[15] = 0.05
        data[16] = 1.0
        data[17] = 300
        data[18] = 0

        # Kokoro (19-20)
        data[19] = self._voice if self._engine == "kokoro" else "af_heart"
        data[20] = 1.0

        # Fish (21-27)
        data[22] = ""
        data[23] = 0.8
        data[24] = 0.8
        data[25] = 1.1
        data[26] = 1024

        # IndexTTS (28-30)
        data[29] = 0.8

        # IndexTTS2 (31-50)
        data[32] = "audio_reference"
        data[34] = ""
        data[35] = 1.0
        data[43] = 1
        data[44] = 0.8
        data[45] = 0.9
        data[46] = 50
        data[47] = 1.1
        data[48] = 1500
        data[50] = False

        # F5 (51-56)
        data[53] = 1.0
        data[54] = 0.15
        data[55] = False
        data[56] = 0

        # Higgs (57-66)
        data[58] = ""
        data[59] = "EMPTY"
        data[60] = ""
        data[61] = 1.0
        data[62] = 0.95
        data[63] = 50
        data[64] = 1024
        data[65] = 7
        data[66] = 2

        # KittenTTS voice (67)
        data[67] = self._voice if self._engine == "kitten_tts" else "expr-voice-2-f"

        # VoxCPM (68-77)
        data[70] = 2.0
        data[71] = 10
        data[72] = True
        data[73] = True
        data[74] = True
        data[75] = 3
        data[76] = 6.0
        data[77] = -1

        # Audio effects (78-91) — all disabled
        data[78] = 0
        data[79] = False
        data[80] = 0
        data[81] = 0
        data[82] = 0
        data[83] = False
        data[84] = 0.3
        data[85] = 0.5
        data[86] = 0.3
        data[87] = False
        data[88] = 0.3
        data[89] = 0.5
        data[90] = False
        data[91] = 0

        return data

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """Synthesize text to audio frames via Gradio predict API."""
        logger.debug("UltimateTTS run_tts: %s", text[:80])
        yield TTSStartedFrame()

        try:
            if not self._client:
                self._client = httpx.AsyncClient(timeout=self._timeout)

            params = self._build_params(text)

            resp = await self._client.post(
                f"{self._predict_url}/generate_unified_tts",
                json={"data": params},
                timeout=self._timeout,
            )

            if resp.status_code != 200:
                logger.error("TTS API error: %s %s", resp.status_code, resp.text[:200])
                yield ErrorFrame(f"TTS API error: {resp.status_code}")
                yield TTSStoppedFrame()
                return

            result = resp.json()
            result_data = result.get("data", [])

            if not isinstance(result_data, list) or len(result_data) < 2:
                logger.error("Unexpected TTS response: %s", str(result)[:200])
                yield ErrorFrame("Unexpected TTS response shape")
                yield TTSStoppedFrame()
                return

            # Check error status
            status = result_data[1] if len(result_data) > 1 else ""
            if isinstance(status, str) and "\u274c" in status:
                logger.error("TTS synthesis error: %s", status)
                yield ErrorFrame(status)
                yield TTSStoppedFrame()
                return

            # Extract audio URL
            audio_info = result_data[0]
            audio_url = None
            if isinstance(audio_info, dict) and "url" in audio_info:
                audio_url = audio_info["url"]
            elif isinstance(audio_info, str) and audio_info.startswith("http"):
                audio_url = audio_info

            if not audio_url:
                logger.error("No audio URL in TTS response: %s", str(audio_info)[:200])
                yield ErrorFrame("No audio URL in TTS response")
                yield TTSStoppedFrame()
                return

            # Download WAV and extract raw PCM
            audio_resp = await self._client.get(audio_url, timeout=30.0)
            if audio_resp.status_code != 200:
                yield ErrorFrame(f"Audio download failed: {audio_resp.status_code}")
                yield TTSStoppedFrame()
                return

            wav_bytes = audio_resp.content
            try:
                with io.BytesIO(wav_bytes) as buf:
                    with wave.open(buf, "rb") as wf:
                        sample_rate = wf.getframerate()
                        num_channels = wf.getnchannels()
                        pcm_data = wf.readframes(wf.getnframes())
                        yield TTSAudioRawFrame(
                            audio=pcm_data,
                            sample_rate=sample_rate,
                            num_channels=num_channels,
                        )
            except wave.Error:
                # If not a valid WAV, yield raw bytes as single-channel PCM
                yield TTSAudioRawFrame(
                    audio=wav_bytes,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                )

            logger.info(
                "UltimateTTS synthesized %d bytes (engine=%s)",
                len(wav_bytes), self._engine,
            )

        except httpx.TimeoutException as exc:
            logger.error("TTS timeout: %s", exc)
            yield ErrorFrame(f"TTS timeout: {exc}")
        except Exception as exc:
            logger.error("TTS error: %s", exc)
            yield ErrorFrame(f"TTS error: {exc}")

        yield TTSStoppedFrame()
