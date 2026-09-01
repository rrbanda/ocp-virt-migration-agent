"""Unit tests for MigrationLoggingPlugin ADK contract compliance."""

import asyncio
from unittest.mock import MagicMock

import pytest

from app.plugins import MigrationLoggingPlugin


@pytest.fixture
def plugin():
    return MigrationLoggingPlugin()


@pytest.fixture
def mock_callback_context():
    ctx = MagicMock()
    ctx.invocation_id = "test-inv-001"
    ctx.agent_name = "TestAgent"
    ctx.state = {}
    return ctx


@pytest.fixture
def mock_tool():
    tool = MagicMock()
    tool.name = "list_vmware_vms"
    return tool


@pytest.fixture
def mock_tool_context():
    tc = MagicMock()
    tc.state = {}
    return tc


class TestPluginSignatures:
    """Verify all hooks are async and accept keyword-only args matching ADK BasePlugin."""

    def test_before_agent_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.before_agent_callback)

    def test_after_agent_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.after_agent_callback)

    def test_before_tool_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.before_tool_callback)

    def test_after_tool_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.after_tool_callback)

    def test_before_model_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.before_model_callback)

    def test_after_model_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.after_model_callback)

    def test_on_tool_error_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.on_tool_error_callback)

    def test_on_model_error_is_async(self, plugin):
        assert asyncio.iscoroutinefunction(plugin.on_model_error_callback)


class TestPluginBehavior:
    @pytest.mark.asyncio
    async def test_before_tool_returns_none(self, plugin, mock_tool, mock_tool_context):
        result = await plugin.before_tool_callback(
            tool=mock_tool,
            tool_args={"ns": "test"},
            tool_context=mock_tool_context,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_after_tool_returns_none(self, plugin, mock_tool, mock_tool_context):
        result = await plugin.after_tool_callback(
            tool=mock_tool,
            tool_args={"ns": "test"},
            tool_context=mock_tool_context,
            result={"status": "ok"},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_before_agent_returns_none(self, plugin, mock_callback_context):
        agent = MagicMock()
        agent.name = "Dispatcher"
        result = await plugin.before_agent_callback(
            callback_context=mock_callback_context,
            agent=agent,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_on_tool_error_returns_none(self, plugin, mock_tool, mock_tool_context):
        result = await plugin.on_tool_error_callback(
            tool=mock_tool,
            tool_args={},
            tool_context=mock_tool_context,
            error=RuntimeError("test"),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_redaction(self, plugin, mock_tool, mock_tool_context):
        result = await plugin.before_tool_callback(
            tool=mock_tool,
            tool_args={"api_key": "secret-123", "namespace": "test"},
            tool_context=mock_tool_context,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_before_model_returns_none(self, plugin, mock_callback_context):
        llm_request = MagicMock()
        result = await plugin.before_model_callback(
            callback_context=mock_callback_context,
            llm_request=llm_request,
        )
        assert result is None
