"""Core service for FRIDAY 2.0.

Runs an asyncio event loop in a dedicated thread with Qt
signals/slots for UI communication.
"""

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Signal

from friday.core.logging import get_logger
from friday.gateway import errors
from friday.gateway.base import Provider
from friday.gateway.types import (
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_TOKEN,
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_USER,
    Message,
)

logger = get_logger(__name__)


@dataclass
class PingMessage:
    """Ping message with timestamp."""

    timestamp: float
    payload: str = "ping"


@dataclass
class PongMessage:
    """Pong message with timestamp."""

    timestamp: float
    original_payload: str


class CoreSignals(QObject):
    """Qt signals for core service communication."""

    # Signal emitted when core has started
    started = Signal()

    # Signal emitted when core has stopped
    stopped = Signal()

    # Signal emitted when a pong is received
    pong_received = Signal(str)

    # Signal emitted when an error occurs
    error_occurred = Signal(str)

    # Streaming chat signals
    token = Signal(str)
    message_done = Signal(str)
    chat_error = Signal(str, str)
    chat_cancelled = Signal()


class CoreService:
    """Core service running asyncio loop in a dedicated thread."""

    def __init__(
        self,
        *,
        settings=None,
        provider: Provider | None = None,
        secret_manager=None,
    ):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._signals = CoreSignals()
        self._ping_queue: asyncio.Queue = asyncio.Queue()
        self._stop_event: Optional[asyncio.Event] = None

        self._settings = settings
        self._secrets = secret_manager
        self._provider = provider
        self._owns_provider = provider is None
        self._history: list[Message] = []
        self._chat_task: asyncio.Task | None = None

    @property
    def signals(self) -> CoreSignals:
        return self._signals

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def history(self) -> tuple[Message, ...]:
        """Return the in-memory conversation history."""
        return tuple(self._history)

    def start(self) -> None:
        """Start the core service in a dedicated thread."""
        if self._running:
            logger.warning("Core service already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="friday-core", daemon=True
        )
        self._thread.start()

        # Wait for the loop to be ready
        timeout = 5.0
        start_time = time.time()
        while self._loop is None and time.time() - start_time < timeout:
            time.sleep(0.01)

        if self._loop is None:
            self._running = False
            raise RuntimeError("Core service failed to start: event loop not ready")

        logger.info("Core service started")

    def stop(self) -> None:
        """Stop the core service cleanly."""
        if not self._running or self._loop is None:
            logger.debug("Core service already stopped")
            return

        logger.info("Stopping core service...")

        # Schedule stop on the event loop
        if self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        self._running = False
        self._loop = None
        self._stop_event = None
        logger.info("Core service stopped")

    def chat_send(self, text: str) -> None:
        """Start a chat request from the UI thread."""
        if not self._running or self._loop is None:
            raise RuntimeError("Core service not running")

        stripped = text.strip()
        if not stripped:
            return

        self._loop.call_soon_threadsafe(self._schedule_chat, stripped)

    def cancel_chat(self) -> None:
        """Cancel the in-flight chat request, if any."""
        if not self._running or self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._cancel_chat)

    def clear_chat(self) -> None:
        """Cancel any in-flight request and clear the session history."""
        if not self._running or self._loop is None:
            self._history.clear()
            return
        self._loop.call_soon_threadsafe(self._clear_chat)

    def send_ping(self, payload: str = "ping") -> None:
        """Send a ping to the core service from the UI thread."""
        if not self._running or self._loop is None:
            raise RuntimeError("Core service not running")

        ping = PingMessage(timestamp=time.time(), payload=payload)
        # Put on the queue from the UI thread
        self._loop.call_soon_threadsafe(self._ping_queue.put_nowait, ping)

    def _schedule_chat(self, text: str) -> None:
        """Schedule a chat task on the core loop (runs on the core thread)."""
        if self._chat_task is not None and not self._chat_task.done():
            self._signals.chat_error.emit(
                "Busy",
                "A reply is already streaming. "
                "Wait for it to finish or press Stop.",
            )
            return
        self._chat_task = asyncio.ensure_future(self._run_chat(text))

    def _cancel_chat(self) -> None:
        task = self._chat_task
        if task is not None and not task.done():
            task.cancel()

    def _clear_chat(self) -> None:
        task = self._chat_task
        if task is not None and not task.done():
            task.cancel()
        self._history.clear()

    def _system_prompt(self) -> str:
        if self._settings is not None:
            return self._settings.provider.system_prompt
        from friday.config.settings import ProviderSettings

        return ProviderSettings().system_prompt

    def _ensure_provider(self) -> Provider:
        if self._provider is not None:
            return self._provider

        from friday.config.settings import load_settings
        from friday.gateway.openai_compat import OpenAICompatProvider

        if self._settings is None:
            self._settings = load_settings()
        self._provider = OpenAICompatProvider(
            self._settings.provider,
            self._secrets,
        )
        self._owns_provider = True
        return self._provider

    async def _run_chat(self, text: str) -> None:
        parts: list[str] = []
        try:
            provider = self._ensure_provider()

            messages: list[Message] = []
            system_prompt = self._system_prompt()
            if system_prompt:
                messages.append(Message(ROLE_SYSTEM, system_prompt))
            messages.extend(self._history)
            messages.append(Message(ROLE_USER, text))

            async for event in provider.stream_chat(messages):
                if event.type == EVENT_TOKEN:
                    if event.text:
                        parts.append(event.text)
                        self._signals.token.emit(event.text)
                elif event.type == EVENT_ERROR:
                    raise event.error or errors.MalformedResponse(
                        "Provider emitted an empty error event."
                    )
                elif event.type == EVENT_DONE:
                    break

            full_text = "".join(parts)
            if not full_text.strip():
                self._signals.chat_error.emit(
                    "MalformedResponse",
                    "The provider returned an empty response.",
                )
                return

            self._history.append(Message(ROLE_USER, text))
            self._history.append(Message(ROLE_ASSISTANT, full_text))
            self._signals.message_done.emit(full_text)

        except errors.Cancelled:
            self._signals.chat_cancelled.emit()
        except errors.GatewayError as exc:
            self._signals.chat_error.emit(exc.kind, str(exc))
        except asyncio.CancelledError:
            self._signals.chat_cancelled.emit()
            raise
        except Exception as exc:
            logger.exception("Chat request failed")
            self._signals.chat_error.emit(exc.__class__.__name__, str(exc))

    def _run_loop(self) -> None:
        """Run the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()

        try:
            self._loop.run_until_complete(self._main())
        except Exception as e:
            logger.exception("Core service loop error: %s", e)
            self._signals.error_occurred.emit(str(e))
        finally:
            try:
                # Cancel all pending tasks
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            finally:
                self._loop.close()
                self._loop = None

    async def _main(self) -> None:
        """Main async entry point."""
        logger.debug("Core async loop started")
        self._signals.started.emit()

        # Process ping queue
        ping_task = asyncio.create_task(self._process_pings())
        stop_task = asyncio.create_task(self._stop_event.wait())

        done, pending = await asyncio.wait(
            [ping_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._shutdown_chat()
        await self._close_provider()

        self._signals.stopped.emit()
        logger.debug("Core async loop stopped")

    async def _shutdown_chat(self) -> None:
        task = self._chat_task
        self._chat_task = None
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Chat task ended during shutdown", exc_info=True)

    async def _close_provider(self) -> None:
        if not self._owns_provider or self._provider is None:
            return
        provider = self._provider
        self._provider = None
        close = getattr(provider, "aclose", None)
        if close is None:
            return
        try:
            await close()
        except Exception:
            logger.exception("Failed to close provider")

    async def _process_pings(self) -> None:
        """Process ping messages from the queue."""
        while self._running:
            try:
                # Wait for ping with timeout to allow checking _running
                ping = await asyncio.wait_for(self._ping_queue.get(), timeout=0.1)
                await self._handle_ping(ping)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error processing ping: %s", e)

    async def _handle_ping(self, ping: PingMessage) -> None:
        """Handle a ping message."""
        pong = PongMessage(
            timestamp=time.time(),
            original_payload=ping.payload,
        )
        # Emit signal on the main thread via call_soon_threadsafe
        if self._loop:
            self._loop.call_soon_threadsafe(
                self._signals.pong_received.emit,
                f"pong at {pong.timestamp:.3f} (re: {pong.original_payload})",
            )
