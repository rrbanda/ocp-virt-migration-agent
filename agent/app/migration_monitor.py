"""Custom BaseAgent for LoopAgent termination during migration monitoring.

Checks the migration status in session state and escalates (stops the
LoopAgent) when the migration reaches a terminal state. Introduces a
configurable polling delay between iterations.

Configuration via environment variables:
  MONITOR_POLL_INTERVAL - Seconds to sleep between poll iterations (default: 15)
"""

import asyncio
import logging
import os
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

log = logging.getLogger(__name__)

try:
    MONITOR_POLL_INTERVAL = max(1, int(os.environ.get("MONITOR_POLL_INTERVAL", "15")))
except (ValueError, TypeError):
    MONITOR_POLL_INTERVAL = 15
    log.warning("Invalid MONITOR_POLL_INTERVAL, using default: %d", MONITOR_POLL_INTERVAL)

_TERMINAL_KEYWORDS = frozenset({
    "Completed", "Failed", "Succeeded", "Error", "Canceled", "Cancelled",
})


class MigrationStatusChecker(BaseAgent):
    """Reads migration_status from session state and escalates when terminal."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = getattr(ctx.session, "state", None) or {}
        status = str(state.get("migration_status", ""))
        is_done = any(kw in status for kw in _TERMINAL_KEYWORDS)

        if not is_done:
            await asyncio.sleep(MONITOR_POLL_INTERVAL)

        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(escalate=is_done),
        )
