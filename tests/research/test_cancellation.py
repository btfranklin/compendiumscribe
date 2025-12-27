"""Tests for the cancellation module."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from compendiumscribe.research.cancellation import CancellationContext
from compendiumscribe.research.errors import ResearchCancelledError
from compendiumscribe.research.execution import execute_deep_research
from compendiumscribe.research.config import ResearchConfig


class TestCancellationContext:
    """Tests for CancellationContext state management."""

    def test_initial_state_is_not_cancelled(self):
        ctx = CancellationContext(client=None)
        assert ctx.is_cancel_requested is False
        assert ctx.response_id is None

    def test_register_response_stores_id(self):
        ctx = CancellationContext(client=None)
        ctx.register_response("resp_123")
        assert ctx.response_id == "resp_123"

    def test_request_cancel_sets_flag(self):
        ctx = CancellationContext(client=None)
        ctx.request_cancel()
        assert ctx.is_cancel_requested is True

    def test_request_cancel_is_idempotent(self):
        client = MagicMock()
        ctx = CancellationContext(client=client)
        ctx.register_response("resp_123")

        ctx.request_cancel()
        ctx.request_cancel()  # Second call

        # Should only call cancel once
        assert client.responses.cancel.call_count == 1

    def test_request_cancel_calls_api_when_response_registered(self):
        client = MagicMock()
        ctx = CancellationContext(client=client)
        ctx.register_response("resp_abc")

        ctx.request_cancel()

        client.responses.cancel.assert_called_once_with("resp_abc")

    def test_request_cancel_handles_api_error_gracefully(self):
        client = MagicMock()
        client.responses.cancel.side_effect = Exception("API error")
        ctx = CancellationContext(client=client)
        ctx.register_response("resp_fail")

        # Should not raise
        ctx.request_cancel()
        assert ctx.is_cancel_requested is True


class TestPollingWithCancellation:
    """Tests for cancelled status detection in polling."""

    def test_polling_raises_cancelled_error_on_cancelled_status(self):
        """Verify polling raises ResearchCancelledError on cancelled status."""
        pending = SimpleNamespace(
            id="resp_cancel_test",
            status="in_progress",
            output=[],
        )
        cancelled = SimpleNamespace(
            id="resp_cancel_test",
            status="cancelled",
            output=[],
        )

        class CancellingResponses:
            def __init__(self):
                self.retrieve_count = 0

            def create(self, **kwargs):
                return pending

            def retrieve(self, response_id: str):
                self.retrieve_count += 1
                return cancelled

        responses = CancellingResponses()
        client = SimpleNamespace(responses=responses)

        config = ResearchConfig(
            background=True,
            polling_interval_seconds=0,
            max_poll_time_minutes=1,
        )

        with pytest.raises(ResearchCancelledError) as excinfo:
            execute_deep_research(client, "prompt", config)

        assert excinfo.value.research_id == "resp_cancel_test"
