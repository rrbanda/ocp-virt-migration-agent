"""Unit tests for migration safety callbacks.

The readiness gate (NOT READY check) is now handled by the ADK 2.0 graph
router (readiness_router), not the callback. Only the dry-run gate and
audit logging remain in the callback.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app.callbacks import migration_safety_callback


@pytest.fixture()
def _mock_tool():
    tool = MagicMock()
    tool.name = "create_migration_plan"
    return tool


@pytest.fixture()
def _other_tool():
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

    def test_non_migration_tool_passes_through(self, _other_tool, _tool_context):
        result = migration_safety_callback(_other_tool, {"namespace": "ns"}, _tool_context)
        assert result is None

    @patch.dict(os.environ, {"MIGRATION_DRY_RUN": "true"})
    def test_dry_run_blocks_migration(self, _mock_tool, _tool_context):
        from importlib import reload

        import app.callbacks

        reload(app.callbacks)
        from app.callbacks import migration_safety_callback as cb

        result = cb(_mock_tool, {"namespace": "ns", "vm_name": "vm1"}, _tool_context)
        assert result is not None
        assert result["status"] == "dry_run"
        assert "vm1" in result["message"]

    @patch.dict(os.environ, {"MIGRATION_DRY_RUN": "false"})
    def test_normal_mode_allows_migration(self, _mock_tool, _tool_context):
        from importlib import reload

        import app.callbacks

        reload(app.callbacks)
        from app.callbacks import migration_safety_callback as cb

        result = cb(_mock_tool, {"namespace": "ns", "vm_name": "vm1"}, _tool_context)
        assert result is None
