"""Unit tests for rollback tools."""

from unittest.mock import MagicMock, patch

from app.tools.rollback_tools import rollback_migration


class TestRollbackMigration:

    @patch("app.tools.rollback_tools.K8S_AVAILABLE", False)
    def test_returns_error_when_k8s_unavailable(self):
        result = rollback_migration("ns", "plan-1")
        assert "error" in result

    def test_empty_namespace_returns_error(self):
        result = rollback_migration("", "plan-1")
        assert "error" in result
        assert "namespace" in result["error"]

    def test_empty_plan_name_returns_error(self):
        result = rollback_migration("ns", "")
        assert "error" in result
        assert "plan_name" in result["error"]

    @patch("app.tools.rollback_tools.K8S_AVAILABLE", True)
    @patch("app.tools.rollback_tools.mtv_custom_api")
    def test_deletes_all_four_crs(self, mock_api):
        mock_client = MagicMock()
        mock_api.return_value = mock_client

        result = rollback_migration("ns", "my-plan")

        assert result["status"] == "rolled_back"
        assert len(result["deleted"]) == 4
        assert mock_client.delete_namespaced_custom_object.call_count == 4

    @patch("app.tools.rollback_tools.K8S_AVAILABLE", True)
    @patch("app.tools.rollback_tools.mtv_custom_api")
    def test_handles_404_gracefully(self, mock_api):
        from app.tools.rollback_tools import ApiException
        mock_client = MagicMock()
        err = ApiException(status=404, reason="Not Found")
        mock_client.delete_namespaced_custom_object.side_effect = err
        mock_api.return_value = mock_client

        result = rollback_migration("ns", "gone-plan")

        assert result["status"] == "rolled_back"
        assert len(result["skipped"]) == 4
        assert len(result["deleted"]) == 0
