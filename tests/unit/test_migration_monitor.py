"""Unit tests for ADK 2.0 graph router functions."""

from unittest.mock import MagicMock


def _mock_ctx(state=None):
    """Create a mock workflow Context with state dict."""
    ctx = MagicMock()
    ctx.state = state if state is not None else {}
    return ctx


class TestIntentRouter:
    def test_pipeline_keyword(self):
        from app.agent import intent_router

        result = intent_router({"action": "PIPELINE: haproxy-user1 in mtv-user1"})
        assert result.actions.route == "pipeline"

    def test_full_migration_keyword(self):
        from app.agent import intent_router

        result = intent_router({"action": "RUN MIGRATION for database-user1"})
        assert result.actions.route == "pipeline"

    def test_batch_keyword(self):
        from app.agent import intent_router

        result = intent_router({"action": "BATCH: 10 RHEL 8 VMs"})
        assert result.actions.route == "batch"

    def test_adhoc_query(self):
        from app.agent import intent_router

        result = intent_router({"action": "Here are the VMware VMs found in mtv-user1..."})
        assert result.actions.route == "done"


class TestReadinessRouter:
    def test_not_ready(self):
        from app.agent import readiness_router

        result = readiness_router({"verdict": "Verdict: NOT READY -- 3 blockers found"})
        assert result.actions.route == "not_ready"

    def test_ready(self):
        from app.agent import readiness_router

        result = readiness_router({"verdict": "READY -- low risk, proceed"})
        assert result.actions.route == "ready"

    def test_ready_with_warnings(self):
        from app.agent import readiness_router

        result = readiness_router({"verdict": "READY WITH WARNINGS -- 2 warnings"})
        assert result.actions.route == "ready"


class TestApprovalRouter:
    def test_yes_approves(self):
        from app.agent import approval_router

        for word in ["yes", "Yes", "y", "approve", "approved", "proceed"]:
            result = approval_router(word)
            assert result.actions.route == "approved", f"'{word}' should approve"

    def test_no_rejects(self):
        from app.agent import approval_router

        for word in ["no", "No", "cancel", "nope", ""]:
            result = approval_router(word)
            assert result.actions.route == "rejected", f"'{word}' should reject"


class TestMonitorRouter:
    def test_completed(self):
        from app.agent import monitor_router

        ctx = _mock_ctx({"temp:monitor_poll_count": 0})
        result = monitor_router(ctx, {"status": "Phase: Completed, all VMs migrated"})
        assert result.actions.route == "completed"

    def test_failed(self):
        from app.agent import monitor_router

        ctx = _mock_ctx({"temp:monitor_poll_count": 0})
        result = monitor_router(ctx, {"status": "Phase: Failed, 2 VMs failed"})
        assert result.actions.route == "failed"

    def test_running(self):
        from app.agent import monitor_router

        ctx = _mock_ctx({"temp:monitor_poll_count": 0})
        result = monitor_router(ctx, {"status": "Phase: Running, 2 of 5 VMs completed"})
        assert result.actions.route == "running"

    def test_empty(self):
        from app.agent import monitor_router

        ctx = _mock_ctx({"temp:monitor_poll_count": 0})
        result = monitor_router(ctx, {"status": ""})
        assert result.actions.route == "running"

    def test_timeout_after_max_polls(self):
        from app.agent import _MAX_MONITOR_POLLS, monitor_router

        ctx = _mock_ctx({"temp:monitor_poll_count": _MAX_MONITOR_POLLS - 1})
        result = monitor_router(ctx, {"status": "Still running"})
        assert result.actions.route == "failed"
        assert "timeout" in str(result.output).lower()
