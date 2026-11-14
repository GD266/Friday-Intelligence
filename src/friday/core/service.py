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


class CoreService:
    """Core service running asyncio loop in a dedicated thread."""

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._signals = CoreSignals()
        self._ping_queue: asyncio.Queue = asyncio.Queue()
        self._stop_event: Optional[asyncio.Event] = None

    @property
    def signals(self) -> CoreSignals:
        return self._signals

    @property
    def is_running(self) -> bool:
        return self._running

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
            logger.warning("Core service not running")
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

        self._signals.stopped.emit()
        logger.debug("Core async loop stopped")

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

    def send_ping(self, payload: str = "ping") -> None:
        """Send a ping to the core service from the UI thread."""
        if not self._running or self._loop is None:
            raise RuntimeError("Core service not running")

        ping = PingMessage(timestamp=time.time(), payload=payload)
        # Put on the queue from the UI thread
        self._loop.call_soon_threadsafe(self._ping_queue.put_nowait, ping)
