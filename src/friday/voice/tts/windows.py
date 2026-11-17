"""Windows TTS engine using SAPI through pywin32 (offline).

How SAPI is reached
-------------------
``pywin32``'s ``win32com.client.Dispatch`` opens an in-process COM object for
``SAPI.SpVoice``.  Speech text is handed to the COM method ``Speak`` (or written
to an ``SAPI.SpFileStream``) directly; it is never interpolated into a command
line.  This module does not use ``subprocess``, PowerShell, ``cscript`` or any
other shell, so clipboard-derived text cannot become shell syntax.
"""

from __future__ import annotations

import asyncio
import locale
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from friday.config.settings import get_default_voice_tmp_dir
from friday.voice.errors import (
    TTSBadVoice,
    TTSEmptyText,
    TTSNetworkError,
    TTSNotAvailable,
    TTSTimeout,
)
from friday.voice.tts.base import SynthesisResult, TTSEngine, Voice

DEFAULT_TIMEOUT = 10.0

# SAPI constants (the dynamic dispatch does not expose SpeechLib).
SSFM_CREATE_FOR_WRITE = 3
SVSF_DEFAULT = 0  # synchronous, plain text (never SVSFIsXML)

_DESCRIPTION_LOCALE = re.compile(r"\(([^)]+)\)\s*$")


def _com_modules() -> tuple[Any, Any]:
    """Import pywin32 lazily and turn a missing dependency into a typed error."""
    try:
        import pythoncom
        import win32com.client as win32com_client
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise TTSNotAvailable(
            "Windows TTS requires pywin32. Install it with: pip install pywin32"
        ) from exc
    return pythoncom, win32com_client


def _locale_from_token(token: Any) -> str:
    """Best-effort locale for a SAPI voice token (e.g. ``en-US``)."""
    try:
        language = int(token.GetAttribute("Language"))
    except Exception:
        return ""
    name = locale.windows_locale.get(language)
    return name.replace("_", "-") if name else ""


def _gender_from_token(token: Any) -> str:
    try:
        gender = str(token.GetAttribute("Gender")).strip()
    except Exception:
        return "Other"
    return gender or "Other"


def _locale_from_description(description: str) -> str:
    """Fallback locale guess used when the registry attribute is missing."""
    match = _DESCRIPTION_LOCALE.search(description)
    return match.group(1) if match else ""


def _resolve_voice(voices: list[Voice], requested: str) -> Voice | None:
    """Match a configured voice by engine id or human-readable name."""
    if not voices:
        return None
    if not requested:
        # No voice configured: use the engine's default (first) voice.
        return voices[0]
    wanted = requested.strip().lower()
    for voice in voices:
        if voice.engine_id.lower() == wanted or voice.name.lower() == wanted:
            return voice
    for voice in voices:
        if wanted in voice.name.lower() or wanted in voice.engine_id.lower():
            return voice
    return None


class WindowsTTSEngine(TTSEngine):
    """Windows TTS engine using SAPI through pywin32 (offline)."""

    name = "windows"

    def __init__(
        self, *, timeout: float = DEFAULT_TIMEOUT, tmp_dir: str = ""
    ) -> None:
        self._timeout = timeout
        self._tmp_dir = (
            Path(tmp_dir) if tmp_dir else Path(get_default_voice_tmp_dir())
        )
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._voices_cache: list[Voice] | None = None

    async def list_voices(self) -> list[Voice]:
        if self._voices_cache is not None:
            return self._voices_cache

        def _list_voices() -> list[Voice]:
            pythoncom, win32com_client = _com_modules()
            pythoncom.CoInitialize()
            voice_obj = None
            try:
                voice_obj = win32com_client.Dispatch("SAPI.SpVoice")
                tokens = voice_obj.GetVoices()
                result: list[Voice] = []
                for index in range(tokens.Count):
                    token = tokens.Item(index)
                    description = token.GetDescription()
                    result.append(
                        Voice(
                            name=description,
                            locale=(
                                _locale_from_token(token)
                                or _locale_from_description(description)
                            ),
                            gender=_gender_from_token(token),
                            age="Other",
                            engine_id=token.Id,
                        )
                    )
                return result
            finally:
                voice_obj = None
                pythoncom.CoUninitialize()

        try:
            voices = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, _list_voices),
                timeout=5.0,
            )
        except asyncio.TimeoutError as exc:
            raise TTSNotAvailable(
                "Windows TTS voice enumeration timed out"
            ) from exc

        self._voices_cache = voices
        return voices

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate_percent: int,
    ) -> SynthesisResult:
        if not text.strip():
            raise TTSEmptyText("Text is empty after preparation")

        voices = await self.list_voices()
        match = _resolve_voice(voices, voice)
        if match is None:
            raise TTSBadVoice(f"Voice '{voice}' not found in Windows TTS voices")

        fd, tmp_path = tempfile.mkstemp(
            suffix=".wav", prefix="friday_tts_", dir=str(self._tmp_dir)
        )
        os.close(fd)
        path = Path(tmp_path)

        def _synthesize() -> None:
            pythoncom, win32com_client = _com_modules()
            pythoncom.CoInitialize()
            voice_obj = None
            stream = None
            try:
                voice_obj = win32com_client.Dispatch("SAPI.SpVoice")
                tokens = voice_obj.GetVoices()
                for index in range(tokens.Count):
                    token = tokens.Item(index)
                    if token.Id == match.engine_id:
                        voice_obj.Voice = token
                        break

                # SAPI Rate is -10..10; voice settings are -50..50 percent.
                voice_obj.Rate = max(-10, min(10, round(rate_percent / 5)))

                stream = win32com_client.Dispatch("SAPI.SpFileStream")
                stream.Open(str(path), SSFM_CREATE_FOR_WRITE)
                voice_obj.AudioOutputStream = stream
                voice_obj.Speak(text, SVSF_DEFAULT)
                stream.Close()
            finally:
                stream = None
                voice_obj = None
                pythoncom.CoUninitialize()

        try:
            await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, _synthesize),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            path.unlink(missing_ok=True)
            raise TTSTimeout(
                f"SAPI synthesis timed out after {self._timeout}s"
            ) from exc
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise TTSNetworkError(f"SAPI synthesis failed: {exc}") from exc

        if not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise TTSNetworkError("SAPI synthesis produced empty file")

        return SynthesisResult(audio_path=str(path), format="wav")

    async def close(self) -> None:
        """No persistent resources to clean up."""
        pass


__all__ = ["WindowsTTSEngine"]
