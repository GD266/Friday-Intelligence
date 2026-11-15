"""Edge TTS engine using the edge-tts library."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import edge_tts

from friday.voice.errors import (
    TTSBadVoice,
    TTSNetworkError,
    TTSTimeout,
)
from friday.voice.tts.base import SynthesisResult, TTSEngine, Voice

DEFAULT_TIMEOUT = 15.0


def _default_voice(voices: list[Voice]) -> Voice | None:
    """Pick a deterministic default without hardcoding a voice id."""
    if not voices:
        return None
    for voice in voices:
        if voice.locale.lower().startswith("en-"):
            return voice
    return voices[0]


class EdgeTTSEngine(TTSEngine):
    """Edge TTS engine using Microsoft's edge-tts library."""

    name = "edge"

    def __init__(
        self,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        proxy: str | None = None,
    ) -> None:
        self._timeout = timeout
        self._proxy = proxy
        self._voices_cache: list[Voice] | None = None

    async def list_voices(self) -> list[Voice]:
        if self._voices_cache is not None:
            return self._voices_cache

        try:
            voices_data = await asyncio.wait_for(
                edge_tts.list_voices(proxy=self._proxy),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TTSTimeout(
                f"Listing voices timed out after {self._timeout}s"
            ) from exc
        except edge_tts.exceptions.UnexpectedResponse as exc:
            from friday.voice.errors import build_tts_http_error

            # UnexpectedResponse has status_code attribute
            status = getattr(exc, 'status_code', getattr(exc, 'status', 500))
            raise build_tts_http_error(status, str(exc)) from exc
        except edge_tts.exceptions.NoAudioReceived as exc:
            raise TTSNetworkError("No audio received from Edge TTS") from exc
        except Exception as exc:
            raise TTSNetworkError(f"Failed to list voices: {exc}") from exc

        voices: list[Voice] = []
        for v in voices_data:
            voices.append(
                Voice(
                    name=v["ShortName"],
                    locale=v["Locale"],
                    gender=v["Gender"],
                    age="Other",
                    engine_id=v["ShortName"],
                )
            )
        self._voices_cache = voices
        return voices

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate_percent: int,
    ) -> SynthesisResult:
        if not text.strip():
            from friday.voice.errors import TTSEmptyText

            raise TTSEmptyText("Text is empty after preparation")

        # Resolve the configured voice. An empty value means "engine default";
        # never hardcode a voice id here.
        voices = await self.list_voices()
        if voice:
            if not any(v.engine_id == voice for v in voices):
                raise TTSBadVoice(
                    f"Voice '{voice}' not found in Edge TTS voices"
                )
            selected_voice = voice
        else:
            default = _default_voice(voices)
            if default is None:
                from friday.voice.errors import TTSNotAvailable

                raise TTSNotAvailable("Edge TTS returned no voices")
            selected_voice = default.engine_id

        # Clamp rate to edge-tts range (-100% to +100%)
        rate = max(-100, min(100, rate_percent))
        rate_str = f"{rate:+d}%"

        # Create temp file for output
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="friday_tts_")
        os.close(fd)
        tmp_path = Path(tmp_path)

        communicate = edge_tts.Communicate(
            text=text,
            voice=selected_voice,
            rate=rate_str,
            proxy=self._proxy,
        )

        try:
            async with asyncio.timeout(self._timeout):
                await communicate.save(str(tmp_path))
        except asyncio.TimeoutError as exc:
            tmp_path.unlink(missing_ok=True)
            raise TTSTimeout(
                f"Synthesis timed out after {self._timeout}s"
            ) from exc
        except edge_tts.exceptions.UnexpectedResponse as exc:
            tmp_path.unlink(missing_ok=True)
            from friday.voice.errors import build_tts_http_error

            status = getattr(exc, 'status_code', getattr(exc, 'status', 500))
            raise build_tts_http_error(status, str(exc)) from exc
        except edge_tts.exceptions.NoAudioReceived as exc:
            tmp_path.unlink(missing_ok=True)
            raise TTSNetworkError("No audio received from Edge TTS") from exc
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise TTSNetworkError(f"Synthesis failed: {exc}") from exc

        # Verify file was created and has content
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise TTSNetworkError("Synthesis produced empty file")

        return SynthesisResult(
            audio_path=str(tmp_path),
            format="mp3",
        )

    async def close(self) -> None:
        """No persistent resources to clean up."""
        pass


__all__ = ["EdgeTTSEngine"]
