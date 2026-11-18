"""Local speech-to-text with Faster-Whisper.

The multilingual ``tiny`` model runs on the CPU with INT8 quantization.
English and Hindi are supported; the language is detected automatically
unless a caller/config override supplies ``en`` or ``hi``.

Model loading and transcription run in worker threads via
:func:`asyncio.to_thread`, so neither the Qt event loop nor the core
asyncio loop is blocked while a model downloads or audio is decoded.
Audio never touches the disk: the recorder's canonical 16 kHz mono int16
PCM is handed to the model as a float32 array, which Faster-Whisper
accepts directly (no container and no temporary file).
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from friday.core.logging import get_logger
from friday.voice.errors import (
    EmptyAudio,
    ModelLoadError,
    TranscriptionError,
    TranscriptionNotAvailable,
    UnsupportedAudioFormat,
)
from friday.voice.stt.base import (
    INPUT_SAMPLE_RATE,
    STATUS_DONE,
    STATUS_LOADING,
    STATUS_PREPARING,
    STATUS_READY,
    STATUS_TRANSCRIBING,
    UNSET,
    StatusCallback,
    TranscriptionResult,
    TranscriptionStatus,
    normalize_language,
)

logger = get_logger(__name__)

DEFAULT_MODEL = "tiny"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_BEAM_SIZE = 5
DOWNLOAD_HEARTBEAT_SECONDS = 5.0

# VAD defaults are the benchmark's conservative "safe" profile: a lower
# speech threshold (0.4) keeps quiet speech, 400 ms padding protects word
# edges and sentence endings, and only pauses longer than 500 ms are
# trimmed.  This preserved every sentence in the English benchmarks and
# removed the trailing-noise hallucination on the Hinglish clip.
DEFAULT_VAD_THRESHOLD = 0.4
DEFAULT_VAD_MIN_SILENCE_MS = 500
DEFAULT_VAD_SPEECH_PAD_MS = 400
DEFAULT_VAD_MIN_SPEECH_MS = 0

MAX_BEAM_SIZE = 10

ModelFactory = Callable[..., Any]


def _validate_beam_size(value: int) -> int:
    """Reject beam sizes Faster-Whisper cannot use."""
    if value < 1 or value > MAX_BEAM_SIZE:
        raise ValueError(
            f"beam_size must be between 1 and {MAX_BEAM_SIZE}, got {value}"
        )
    return value


def _create_whisper_model(**kwargs: Any) -> Any:
    """Construct a real Faster-Whisper model (imported lazily)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - installed in real use
        raise TranscriptionNotAvailable(
            "faster-whisper is not installed. Run: pip install -e ."
        ) from exc
    return WhisperModel(**kwargs)


class FasterWhisperEngine:
    """Faster-Whisper engine configured for CPU/INT8 multilingual use."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        cpu_threads: int = 0,
        language: str = "auto",
        beam_size: int = DEFAULT_BEAM_SIZE,
        vad_filter: bool = True,
        vad_threshold: float = DEFAULT_VAD_THRESHOLD,
        vad_min_silence_ms: int = DEFAULT_VAD_MIN_SILENCE_MS,
        vad_speech_pad_ms: int = DEFAULT_VAD_SPEECH_PAD_MS,
        vad_min_speech_ms: int = DEFAULT_VAD_MIN_SPEECH_MS,
        download_root: str = "",
        on_status: StatusCallback | None = None,
        model_factory: ModelFactory | None = None,
        heartbeat_seconds: float = DOWNLOAD_HEARTBEAT_SECONDS,
    ) -> None:
        cleaned = model.strip()
        if not cleaned:
            raise ValueError("model must not be empty")
        if cleaned.lower().endswith(".en"):
            raise ValueError(
                "English-only Whisper models (.en) are not supported; "
                "use the multilingual model, e.g. 'tiny'."
            )
        if cpu_threads < 0:
            raise ValueError("cpu_threads must be zero or positive")
        if heartbeat_seconds <= 0:
            raise ValueError("heartbeat_seconds must be positive")
        if not 0 < vad_threshold < 1:
            raise ValueError("vad_threshold must be between 0 and 1")
        if vad_min_silence_ms < 0:
            raise ValueError("vad_min_silence_ms must not be negative")
        if vad_speech_pad_ms < 0:
            raise ValueError("vad_speech_pad_ms must not be negative")
        if vad_min_speech_ms < 0:
            raise ValueError("vad_min_speech_ms must not be negative")

        self._model_name = cleaned
        self._cpu_threads = cpu_threads
        self._language = normalize_language(language)
        self._beam_size = _validate_beam_size(beam_size)
        self._vad_filter = bool(vad_filter)
        self._vad_threshold = float(vad_threshold)
        self._vad_min_silence_ms = int(vad_min_silence_ms)
        self._vad_speech_pad_ms = int(vad_speech_pad_ms)
        self._vad_min_speech_ms = int(vad_min_speech_ms)
        self._download_root = download_root.strip()
        self._on_status = on_status
        self._model_factory = model_factory or _create_whisper_model
        self._heartbeat = heartbeat_seconds
        self._model: Any | None = None
        self._loop_locks: dict[
            asyncio.AbstractEventLoop, asyncio.Lock
        ] = {}
        self._build_lock = threading.Lock()
        # A cancelled asyncio task cannot interrupt a worker thread that is
        # already inside the model.  Holding a process-wide lock across the
        # whole decode keeps a late cancellation from overlapping the next
        # transcription.
        self._inference_lock = threading.Lock()

    @property
    def model_name(self) -> str:
        """Return the configured model identifier."""
        return self._model_name

    @property
    def language(self) -> str | None:
        """Return the configured language (``None`` means automatic)."""
        return self._language

    @property
    def beam_size(self) -> int:
        """Return the configured decoding beam size."""
        return self._beam_size

    @property
    def vad_filter(self) -> bool:
        """Return whether voice-activity filtering is enabled by default."""
        return self._vad_filter

    @property
    def is_loaded(self) -> bool:
        """Return True when the model is ready for transcription."""
        return self._model is not None

    def _loop_lock(self) -> asyncio.Lock:
        """Return a per-event-loop lock (the engine is loop-agnostic)."""
        loop = asyncio.get_running_loop()
        lock = self._loop_locks.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            self._loop_locks[loop] = lock
        return lock

    async def load(self) -> None:
        """Download (first run) and load the model without blocking a loop."""
        if self._model is not None:
            return
        async with self._loop_lock():
            if self._model is not None:
                return
            await self._load_locked()

    async def _load_locked(self) -> None:
        started = time.perf_counter()
        local_path = Path(self._model_name)
        if local_path.is_dir():
            self._emit(
                STATUS_PREPARING, f"Loading model from {local_path}..."
            )
        else:
            self._emit(
                STATUS_PREPARING,
                f"Preparing model '{self._model_name}'. The first run "
                "downloads it, which can take a few minutes...",
            )

        kwargs = self._model_kwargs()

        task = asyncio.create_task(
            asyncio.to_thread(self._build_model_sync, kwargs)
        )
        try:
            while True:
                done, _ = await asyncio.wait(
                    {task}, timeout=self._heartbeat
                )
                if done:
                    break
                elapsed = time.perf_counter() - started
                self._emit(
                    STATUS_LOADING,
                    f"Downloading or loading model "
                    f"'{self._model_name}'... {elapsed:.0f}s elapsed",
                    elapsed,
                )
            model = await task
        except asyncio.CancelledError:
            task.cancel()
            raise

        self._model = model
        elapsed = time.perf_counter() - started
        logger.info(
            "stt_model_loaded: model=%s device=%s compute_type=%s "
            "cpu_threads=%d load_ms=%.1f",
            self._model_name,
            DEFAULT_DEVICE,
            DEFAULT_COMPUTE_TYPE,
            self._cpu_threads,
            elapsed * 1000.0,
        )
        self._emit(
            STATUS_READY,
            f"Model '{self._model_name}' ready in {elapsed:.1f}s",
            elapsed,
        )

    def _model_kwargs(self) -> dict[str, Any]:
        """Return the kwargs passed to ``faster_whisper.WhisperModel``."""
        kwargs: dict[str, Any] = {
            "model_size_or_path": self._model_name,
            "device": DEFAULT_DEVICE,
            "compute_type": DEFAULT_COMPUTE_TYPE,
        }
        if self._cpu_threads > 0:
            kwargs["cpu_threads"] = self._cpu_threads
        if self._download_root:
            kwargs["download_root"] = self._download_root
        return kwargs

    def _build_model_sync(self, kwargs: dict[str, Any]) -> Any:
        """Create the model on a worker thread."""
        try:
            with self._build_lock:
                return self._model_factory(**kwargs)
        except (TranscriptionNotAvailable, ModelLoadError):
            raise
        except ImportError as exc:
            raise TranscriptionNotAvailable(
                "faster-whisper is not installed. Run: pip install -e ."
            ) from exc
        except Exception as exc:
            logger.info(
                "stt_model_load_failed: model=%s kind=%s",
                self._model_name,
                type(exc).__name__,
            )
            raise ModelLoadError(
                f"Could not download or load Whisper model "
                f"'{self._model_name}'. Check your internet connection "
                f"and the model name. ({type(exc).__name__}: {exc})"
            ) from exc

    async def transcribe(
        self,
        pcm: bytes,
        *,
        sample_rate: int = INPUT_SAMPLE_RATE,
        language: str | None | object = UNSET,
        beam_size: int | None = None,
        vad_filter: bool | None = None,
        vad_parameters: dict[str, Any] | None = None,
    ) -> TranscriptionResult:
        """Transcribe 16 kHz mono int16 PCM.

        ``language`` is a per-call override.  ``None`` forces automatic
        detection even when the engine has a configured language; omitting
        it uses the configured default.

        ``beam_size``, ``vad_filter`` and ``vad_parameters`` are per-call
        overrides used by the benchmark to compare configurations without
        reloading the model.  Omitted values use the engine configuration.
        """
        requested = (
            self._language
            if language is UNSET
            else normalize_language(language)
        )
        effective_beam = (
            self._beam_size
            if beam_size is None
            else _validate_beam_size(beam_size)
        )
        effective_vad = (
            self._vad_filter if vad_filter is None else bool(vad_filter)
        )
        selected_vad = (
            dict(vad_parameters)
            if effective_vad and vad_parameters is not None
            else (self._vad_options() if effective_vad else None)
        )
        payload = self._prepare_pcm(pcm, sample_rate)

        if self._model is None:
            await self.load()

        async with self._loop_lock():
            self._emit(
                STATUS_TRANSCRIBING,
                f"Transcribing with model '{self._model_name}'...",
            )
            started = time.perf_counter()
            try:
                result = await asyncio.to_thread(
                    self._transcribe_sync,
                    payload,
                    requested,
                    effective_beam,
                    effective_vad,
                    selected_vad,
                )
            except TranscriptionError:
                raise
            except Exception as exc:
                logger.info(
                    "stt_transcription_failed: model=%s kind=%s",
                    self._model_name,
                    type(exc).__name__,
                )
                raise TranscriptionError(
                    f"Transcription failed: {type(exc).__name__}: {exc}"
                ) from exc

        elapsed = time.perf_counter() - started
        # Never log recognised text; only metadata.
        logger.info(
            "stt_transcription_done: model=%s language=%s "
            "language_prob=%.3f audio_s=%.2f chars=%d beam=%d vad=%s "
            "transcribe_ms=%.1f",
            self._model_name,
            result.language or "-",
            result.language_probability,
            result.duration_seconds,
            len(result.text),
            effective_beam,
            effective_vad,
            elapsed * 1000.0,
        )
        self._emit(
            STATUS_DONE,
            f"Transcribed {result.duration_seconds:.1f}s of audio",
            elapsed,
        )
        return result

    @staticmethod
    def _prepare_pcm(pcm: bytes, sample_rate: int) -> bytes:
        """Validate the recorder's canonical PCM and trim a stray byte."""
        if not isinstance(pcm, bytes):
            raise UnsupportedAudioFormat("Audio must be raw PCM bytes")
        if sample_rate != INPUT_SAMPLE_RATE:
            raise UnsupportedAudioFormat(
                f"Expected {INPUT_SAMPLE_RATE} Hz mono audio, got "
                f"{sample_rate} Hz. Convert with "
                "friday.voice.audio.to_mono_16k first."
            )
        usable = len(pcm) - (len(pcm) % 2)
        if usable == 0:
            raise EmptyAudio(
                "The recording is empty; nothing was captured."
            )
        return pcm[:usable]

    def _vad_options(self) -> dict[str, Any]:
        """Return this engine's VAD settings as a Faster-Whisper dict."""
        return {
            "threshold": self._vad_threshold,
            "min_silence_duration_ms": self._vad_min_silence_ms,
            "speech_pad_ms": self._vad_speech_pad_ms,
            "min_speech_duration_ms": self._vad_min_speech_ms,
        }

    @staticmethod
    def _pcm_to_float32(pcm: bytes) -> Any:
        """Normalize int16 PCM to the float32 array Faster-Whisper wants."""
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - faster-whisper dep
            raise TranscriptionNotAvailable(
                "numpy is required for transcription. "
                "Run: pip install -e ."
            ) from exc
        return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0

    def _transcribe_sync(
        self,
        pcm: bytes,
        language: str | None,
        beam_size: int,
        vad_filter: bool,
        vad_parameters: dict[str, Any] | None,
    ) -> TranscriptionResult:
        """Run the model on a worker thread."""
        model = self._model
        if model is None:  # pragma: no cover - guarded by transcribe()
            raise TranscriptionNotAvailable("The Whisper model is not loaded.")
        options: dict[str, Any] = {
            "language": language,
            "beam_size": beam_size,
            "vad_filter": vad_filter,
        }
        if vad_filter and vad_parameters is not None:
            options["vad_parameters"] = vad_parameters
        with self._inference_lock:
            segments, info = model.transcribe(
                self._pcm_to_float32(pcm), **options
            )
            parts: list[str] = []
            count = 0
            for segment in segments:
                parts.append(str(getattr(segment, "text", "")))
                count += 1
        text = "".join(parts).strip()
        detected = getattr(info, "language", None) or language or ""
        probability = getattr(info, "language_probability", 0.0) or 0.0
        duration = getattr(info, "duration", 0.0) or 0.0
        after_vad = (
            getattr(info, "duration_after_vad", None) if vad_filter else None
        )
        if vad_filter and after_vad is None:
            after_vad = duration
        return TranscriptionResult(
            text=text,
            language=str(detected),
            language_probability=float(probability),
            duration_seconds=float(duration),
            duration_after_vad_seconds=(
                None if after_vad is None else float(after_vad)
            ),
            segment_count=count,
        )

    async def close(self) -> None:
        """Drop the model so it can be freed/reloaded."""
        async with self._loop_lock():
            self._model = None

    def _emit(
        self,
        phase: str,
        message: str,
        elapsed: float = 0.0,
    ) -> None:
        """Report a progress update; callback errors never break the engine."""
        callback = self._on_status
        if callback is None:
            return
        try:
            callback(
                TranscriptionStatus(
                    phase=phase, message=message, elapsed_seconds=elapsed
                )
            )
        except Exception:  # pragma: no cover - defensive only
            logger.debug("STT status callback failed", exc_info=True)


__all__ = [
    "DEFAULT_BEAM_SIZE",
    "DEFAULT_COMPUTE_TYPE",
    "DEFAULT_DEVICE",
    "DEFAULT_MODEL",
    "DEFAULT_VAD_MIN_SILENCE_MS",
    "DEFAULT_VAD_MIN_SPEECH_MS",
    "DEFAULT_VAD_SPEECH_PAD_MS",
    "DEFAULT_VAD_THRESHOLD",
    "FasterWhisperEngine",
    "MAX_BEAM_SIZE",
]
