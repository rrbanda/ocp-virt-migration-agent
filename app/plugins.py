"""ADK Plugins for cross-cutting observability and policy enforcement.

Registered via ``App(plugins=[...])`` in ``agent.py``.
"""

import logging
import time
from contextvars import ContextVar

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import BaseTool, ToolContext
from google.genai import types

log = logging.getLogger(__name__)

_REDACTED_KEYS = frozenset({"token", "api_key", "password", "secret"})

_tool_start_time: ContextVar[float | None] = ContextVar("_tool_start_time", default=None)


def _redact(args: dict) -> dict:
    """Return a shallow copy of *args* with sensitive values masked."""
    return {
        k: "***REDACTED***" if any(s in k.lower() for s in _REDACTED_KEYS) else v
        for k, v in args.items()
    }


class MigrationLoggingPlugin(BasePlugin):
    """Structured lifecycle logging across every agent, tool, and model call."""

    def __init__(self) -> None:
        super().__init__(name="migration_logging")

    # -- Agent lifecycle ---------------------------------------------------

    async def before_agent_callback(
        self, *, callback_context: CallbackContext, **kwargs
    ) -> types.Content | None:
        agent: BaseAgent = kwargs.get("agent")
        agent_name = agent.name if agent else "unknown"
        log.info(
            "[plugin] agent_start  name=%s  invocation=%s",
            agent_name, callback_context.invocation_id,
        )
        callback_context.state[f"_plugin_agent_start:{agent_name}"] = time.monotonic()
        return None

    async def after_agent_callback(
        self, *, callback_context: CallbackContext, **kwargs
    ) -> types.Content | None:
        agent: BaseAgent = kwargs.get("agent")
        agent_name = agent.name if agent else "unknown"
        started = callback_context.state.get(f"_plugin_agent_start:{agent_name}")
        duration_ms = round((time.monotonic() - started) * 1000) if started else -1
        log.info(
            "[plugin] agent_end    name=%s  invocation=%s  duration_ms=%d",
            agent_name, callback_context.invocation_id, duration_ms,
        )
        return None

    # -- Tool lifecycle ----------------------------------------------------

    async def before_tool_callback(
        self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext, **kwargs
    ) -> dict | None:
        _tool_start_time.set(time.monotonic())
        log.info(
            "[plugin] tool_start   name=%s  args=%s",
            tool.name, _redact(tool_args),
        )
        return None

    async def after_tool_callback(
        self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext, result: dict, **kwargs
    ) -> dict | None:
        started = _tool_start_time.get()
        duration_ms = round((time.monotonic() - started) * 1000) if started else -1
        status = result.get("status", result.get("error", "ok")) if isinstance(result, dict) else "ok"
        log.info(
            "[plugin] tool_end     name=%s  status=%s  duration_ms=%d",
            tool.name, status, duration_ms,
        )
        return None

    async def on_tool_error_callback(
        self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext, error: Exception, **kwargs
    ) -> dict | None:
        log.error(
            "[plugin] tool_error   name=%s  error=%s  args=%s",
            tool.name, error, _redact(tool_args),
        )
        return None

    # -- Model lifecycle ---------------------------------------------------

    async def before_model_callback(
        self, *, callback_context: CallbackContext, llm_request: LlmRequest, **kwargs
    ) -> LlmResponse | None:
        log.info(
            "[plugin] model_start  agent=%s  invocation=%s",
            callback_context.agent_name, callback_context.invocation_id,
        )
        return None

    async def after_model_callback(
        self, *, callback_context: CallbackContext, llm_response: LlmResponse, **kwargs
    ) -> LlmResponse | None:
        log.info(
            "[plugin] model_end    agent=%s  invocation=%s",
            callback_context.agent_name, callback_context.invocation_id,
        )
        return None

    async def on_model_error_callback(
        self, *, callback_context: CallbackContext, error: Exception, **kwargs
    ) -> LlmResponse | None:
        log.error(
            "[plugin] model_error  agent=%s  error=%s  invocation=%s",
            callback_context.agent_name, error, callback_context.invocation_id,
        )
        return None
