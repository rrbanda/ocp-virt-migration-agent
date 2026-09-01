"""Unit tests for ADK 2.0 graph router functions."""



class TestIntentRouter:

    def test_pipeline_keyword(self):
        from app.agent import intent_router
        result = intent_router("PIPELINE: haproxy-user1 in mtv-user1")
        assert result.actions.route == "pipeline"

    def test_full_migration_keyword(self):
        from app.agent import intent_router
        result = intent_router("RUN MIGRATION for database-user1")
        assert result.actions.route == "pipeline"

    def test_batch_keyword(self):
        from app.agent import intent_router
        result = intent_router("BATCH: 10 RHEL 8 VMs")
        assert result.actions.route == "batch"

    def test_adhoc_query(self):
        from app.agent import intent_router
        result = intent_router("Here are the VMware VMs found in mtv-user1...")
        assert result.actions.route == "done"


class TestReadinessRouter:

    def test_not_ready(self):
        from app.agent import readiness_router
        result = readiness_router("Verdict: NOT READY -- 3 blockers found")
        assert result.actions.route == "not_ready"

    def test_ready(self):
        from app.agent import readiness_router
        result = readiness_router("READY -- low risk, proceed")
        assert result.actions.route == "ready"

    def test_ready_with_warnings(self):
        from app.agent import readiness_router
        result = readiness_router("READY WITH WARNINGS -- 2 warnings")
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
        result = monitor_router("Phase: Completed, all VMs migrated")
        assert result.actions.route == "completed"

    def test_failed(self):
        from app.agent import monitor_router
        result = monitor_router("Phase: Failed, 2 VMs failed")
        assert result.actions.route == "failed"

    def test_running(self):
        from app.agent import monitor_router
        result = monitor_router("Phase: Running, 2 of 5 VMs completed")
        assert result.actions.route == "running"

    def test_empty(self):
        from app.agent import monitor_router
        result = monitor_router("")
        assert result.actions.route == "running"
