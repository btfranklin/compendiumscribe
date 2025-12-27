"""Cancellation support for deep research runs."""
from __future__ import annotations

import signal
from typing import Any, Callable

from .progress import emit_progress


class CancellationContext:
    """Manages cancellation state and signal handling for deep research runs.

    Usage:
        ctx = CancellationContext(client)
        ctx.install_signal_handler()
        try:
            # Run research, passing ctx to relevant functions
            ...
        finally:
            ctx.restore_signal_handler()
    """

    def __init__(self, client: Any, config: Any = None):
        self._client = client
        self._config = config
        self._response_id: str | None = None
        self._cancel_requested = False
        self._original_handler: Callable[..., Any] | int | None = None

    @property
    def is_cancel_requested(self) -> bool:
        """True if cancellation has been requested."""
        return self._cancel_requested

    @property
    def response_id(self) -> str | None:
        """The response ID of the current research run."""
        return self._response_id

    def register_response(self, response_id: str) -> None:
        """Register a response ID for potential cancellation."""
        self._response_id = response_id

    def request_cancel(self) -> None:
        """Request cancellation of the current research run.

        Calls the OpenAI cancel endpoint if a response is registered.
        """
        if self._cancel_requested:
            return

        self._cancel_requested = True

        if self._config:
            emit_progress(
                self._config,
                phase="deep_research",
                status="cancelling",
                message="Research cancellation requested...",
            )

        if self._response_id and self._client:
            try:
                self._client.responses.cancel(self._response_id)
            except Exception:
                # Best effort - cancellation may fail if already complete
                pass

    def install_signal_handler(self) -> None:
        """Install SIGINT handler for graceful cancellation.

        First Ctrl+C requests cancellation.
        Second Ctrl+C raises KeyboardInterrupt for hard exit.
        """
        self._original_handler = signal.getsignal(signal.SIGINT)

        def handler(signum: int, frame: Any) -> None:
            if self._cancel_requested:
                # Second Ctrl+C - hard exit
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                raise KeyboardInterrupt
            else:
                # First Ctrl+C - request cancellation
                self.request_cancel()

        signal.signal(signal.SIGINT, handler)

    def restore_signal_handler(self) -> None:
        """Restore the original SIGINT handler."""
        if self._original_handler is not None:
            signal.signal(signal.SIGINT, self._original_handler)
            self._original_handler = None


__all__ = ["CancellationContext"]
