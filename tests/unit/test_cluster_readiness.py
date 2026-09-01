"""Unit tests for the cluster readiness tool."""

import inspect

from app.tools.cluster_readiness import check_cluster_readiness


class TestCheckClusterReadiness:
    def test_returns_results_dict(self):
        result = check_cluster_readiness("test-ns")
        if "error" in result:
            assert isinstance(result["error"], str)
        else:
            assert "checks" in result
            assert "ready" in result

    def test_storage_class_uses_api_client_attribute(self):
        """Regression test: ensure we use .api_client (not ._api_client)."""
        from app.tools import cluster_readiness

        source = inspect.getsource(cluster_readiness.check_cluster_readiness)
        assert "._api_client" not in source, (
            "Storage class check uses ._api_client which causes AttributeError. Use .api_client instead."
        )
        assert ".api_client" in source
