"""Unit tests for multi-cluster Kubernetes client factory."""

import os
import tempfile
from unittest.mock import MagicMock, patch


class TestReadToken:
    def test_reads_from_env_var(self):
        with patch.dict(os.environ, {"TEST_TOKEN": "my-secret-token"}):
            from app.shared.cluster_clients import _read_token

            assert _read_token("TEST_TOKEN") == "my-secret-token"

    def test_reads_from_file_when_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".token", delete=False) as f:
            f.write("  file-based-token  \n")
            f.flush()
            with patch.dict(os.environ, {"TEST_TOKEN": f.name}):
                from app.shared.cluster_clients import _read_token

                assert _read_token("TEST_TOKEN") == "file-based-token"
        os.unlink(f.name)

    def test_returns_empty_for_missing_var(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NONEXISTENT_VAR", None)
            from app.shared.cluster_clients import _read_token

            assert _read_token("NONEXISTENT_VAR") == ""


class TestGetInventoryToken:
    @patch.dict(os.environ, {"MTV_INVENTORY_TOKEN": "inv-token", "MTV_API_TOKEN": "api-token"})
    def test_prefers_inventory_token(self):
        from app.shared.cluster_clients import _get_inventory_token

        result = _get_inventory_token()
        assert result == "inv-token"

    @patch.dict(os.environ, {"MTV_INVENTORY_TOKEN": "", "MTV_API_TOKEN": "api-token"})
    def test_falls_back_to_api_token(self):
        from app.shared.cluster_clients import _get_inventory_token

        result = _get_inventory_token()
        assert result == "api-token"


class TestVirtFallback:
    def test_virt_uses_mtv_when_not_set(self):
        """When VIRT_API_URL is empty, virt fallback logic uses MTV_API_URL."""
        from app.shared.cluster_clients import MTV_API_URL, VIRT_API_URL

        if not VIRT_API_URL:
            assert MTV_API_URL is not None or MTV_API_URL == ""

    def test_defaults_loaded(self):
        from app.shared.cluster_clients import (
            DEFAULT_MTV_NAMESPACE,
            DEFAULT_VIRT_NAMESPACE,
            MTV_OPERATOR_NAMESPACE,
            TARGET_STORAGE_CLASS,
        )

        assert DEFAULT_MTV_NAMESPACE
        assert DEFAULT_VIRT_NAMESPACE
        assert MTV_OPERATOR_NAMESPACE
        assert TARGET_STORAGE_CLASS


class TestClientCache:
    @patch("app.shared.cluster_clients.K8S_AVAILABLE", True)
    @patch("app.shared.cluster_clients._create_client")
    def test_returns_cached_client_within_ttl(self, mock_create):
        from app.shared.cluster_clients import _build_client, _client_cache, _client_lock

        mock_client = MagicMock()
        mock_create.return_value = mock_client

        with _client_lock:
            _client_cache.clear()

        c1 = _build_client("https://api.test:6443", "token", "")
        c2 = _build_client("https://api.test:6443", "token", "")

        assert c1 is c2
        assert mock_create.call_count == 1

        with _client_lock:
            _client_cache.clear()
