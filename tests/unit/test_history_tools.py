"""Unit tests for migration history tools."""

import json
from unittest.mock import MagicMock

import pytest

from app.tools.history_tools import record_migration, search_migration_history


@pytest.fixture()
def _tool_context():
    tc = MagicMock()
    tc.state = {}
    return tc


@pytest.mark.asyncio
class TestRecordMigration:
    async def test_records_to_session_state(self, _tool_context):
        result = await record_migration(
            vm_name="test-vm",
            namespace="ns",
            status="completed",
            summary="Migration successful",
            tool_context=_tool_context,
        )
        assert result["status"] == "recorded"
        assert "migration_history:test-vm" in _tool_context.state
        record = json.loads(_tool_context.state["migration_history:test-vm"])
        assert record["vm_name"] == "test-vm"
        assert record["status"] == "completed"


@pytest.mark.asyncio
class TestSearchMigrationHistory:
    async def test_finds_matching_records(self, _tool_context):
        _tool_context.state["migration_history:vm1"] = json.dumps(
            {
                "vm_name": "vm1",
                "namespace": "ns",
                "status": "completed",
            }
        )
        _tool_context.state["migration_history:vm2"] = json.dumps(
            {
                "vm_name": "vm2",
                "namespace": "ns",
                "status": "failed",
            }
        )

        result = await search_migration_history("vm1", _tool_context)
        assert result["count"] == 1
        assert result["records"][0]["vm_name"] == "vm1"

    async def test_search_by_status(self, _tool_context):
        _tool_context.state["migration_history:vm1"] = json.dumps(
            {
                "vm_name": "vm1",
                "status": "failed",
            }
        )
        result = await search_migration_history("failed", _tool_context)
        assert result["count"] == 1

    async def test_empty_history(self, _tool_context):
        result = await search_migration_history("anything", _tool_context)
        assert result["count"] == 0
