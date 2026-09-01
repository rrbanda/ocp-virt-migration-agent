"""Unit tests for migration safety callbacks."""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.callbacks import migration_safety_callback


@pytest.fixture()
def _plan_tool():
    tool = MagicMock()
    tool.name = "create_migration_plan"
    return tool


@pytest.fixture()
def _execute_tool():
    tool = MagicMock()
    tool.name = "execute_migration"
    return tool


@pytest.fixture()
def _rollback_tool():
    tool = MagicMock()
    tool.name = "rollback_migration"
    return tool


@pytest.fixture()
def _safe_tool():
    tool = MagicMock()
    tool.name = "list_vmware_vms"
    return tool


@pytest.fixture()
def _tool_context():
    tc = MagicMock()
    tc.state = {}
    return tc


class TestMigrationSafetyCallback:
    """Test the before_tool_callback dry-run guardrail."""

    @pytest.mark.asyncio
    async def test_non_destructive_tool_passes_through(self, _safe_tool, _tool_context):
        result = await migration_safety_callback(_safe_tool, {"namespace": "ns"}, _tool_context)
        assert result is None

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MIGRATION_DRY_RUN": "true"})
    async def test_dry_run_blocks_create_plan(self, _plan_tool, _tool_context):
        from importlib import reload

        import app.callbacks

        reload(app.callbacks)
        from app.callbacks import migration_safety_callback as cb

        result = await cb(_plan_tool, {"namespace": "ns", "vm_name": "vm1"}, _tool_context)
        assert result is not None
        assert result["status"] == "dry_run"
        assert result["tool"] == "create_migration_plan"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MIGRATION_DRY_RUN": "true"})
    async def test_dry_run_blocks_execute(self, _execute_tool, _tool_context):
        from importlib import reload

        import app.callbacks

        reload(app.callbacks)
        from app.callbacks import migration_safety_callback as cb

        result = await cb(_execute_tool, {"namespace": "ns", "plan_name": "plan-1"}, _tool_context)
        assert result is not None
        assert result["status"] == "dry_run"
        assert result["tool"] == "execute_migration"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MIGRATION_DRY_RUN": "true"})
    async def test_dry_run_blocks_rollback(self, _rollback_tool, _tool_context):
        from importlib import reload

        import app.callbacks

        reload(app.callbacks)
        from app.callbacks import migration_safety_callback as cb

        result = await cb(_rollback_tool, {"namespace": "ns", "plan_name": "plan-1"}, _tool_context)
        assert result is not None
        assert result["status"] == "dry_run"
        assert result["tool"] == "rollback_migration"

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"MIGRATION_DRY_RUN": "false"})
    async def test_normal_mode_allows_destructive_tools(self, _plan_tool, _tool_context):
        from importlib import reload

        import app.callbacks

        reload(app.callbacks)
        from app.callbacks import migration_safety_callback as cb

        result = await cb(_plan_tool, {"namespace": "ns", "vm_name": "vm1"}, _tool_context)
        assert result is None
