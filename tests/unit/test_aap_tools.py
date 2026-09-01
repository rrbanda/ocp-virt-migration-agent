"""Unit tests for AAP integration tools."""

import os
from unittest.mock import MagicMock, patch


class TestListJobTemplates:
    @patch.dict(os.environ, {"AAP_URL": "", "AAP_TOKEN": ""})
    def test_returns_error_when_not_configured(self):
        from importlib import reload

        import app.tools.aap_tools

        reload(app.tools.aap_tools)
        result = app.tools.aap_tools.list_job_templates()
        assert "error" in result
        assert "not configured" in result["error"].lower()

    @patch.dict(os.environ, {"AAP_URL": "https://aap.example.com", "AAP_TOKEN": "test-token"})
    def test_returns_templates_on_success(self):
        from importlib import reload

        import app.tools.aap_tools

        reload(app.tools.aap_tools)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"id": 1, "name": "pre-migration", "description": "Pre-mig check", "status": "successful"},
                {"id": 2, "name": "post-migration", "description": "Post-mig check", "status": "successful"},
            ]
        }
        with patch.object(app.tools.aap_tools, "_get", return_value=mock_resp):
            result = app.tools.aap_tools.list_job_templates()
        assert result["count"] == 2
        assert result["templates"][0]["name"] == "pre-migration"


class TestLaunchJob:
    @patch.dict(os.environ, {"AAP_URL": "", "AAP_TOKEN": ""})
    def test_returns_error_when_not_configured(self):
        from importlib import reload

        import app.tools.aap_tools

        reload(app.tools.aap_tools)
        result = app.tools.aap_tools.launch_job(template_id=1)
        assert "error" in result

    @patch.dict(os.environ, {"AAP_URL": "https://aap.example.com", "AAP_TOKEN": "test-token"})
    def test_returns_job_id_on_success(self):
        from importlib import reload

        import app.tools.aap_tools

        reload(app.tools.aap_tools)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 42, "status": "pending"}
        with patch.object(app.tools.aap_tools, "_post", return_value=mock_resp):
            result = app.tools.aap_tools.launch_job(template_id=1)
        assert result["job_id"] == 42


class TestGetJobOutput:
    @patch.dict(os.environ, {"AAP_URL": "https://aap.example.com", "AAP_TOKEN": "t", "AAP_MAX_OUTPUT_BYTES": "100"})
    def test_truncates_large_output(self):
        from importlib import reload

        import app.tools.aap_tools

        reload(app.tools.aap_tools)

        mock_job = MagicMock()
        mock_job.json.return_value = {"id": 1, "status": "successful"}
        mock_output = MagicMock()
        mock_output.text = "A" * 500

        with patch.object(app.tools.aap_tools, "_get", side_effect=[mock_job, mock_output]):
            result = app.tools.aap_tools.get_job_output(job_id=1)
        assert result["truncated"] is True
        assert len(result["output"]) == 100
        assert result["original_length"] == 500

    @patch.dict(os.environ, {"AAP_URL": "https://aap.example.com", "AAP_TOKEN": "t"})
    def test_blocks_running_job(self):
        from importlib import reload

        import app.tools.aap_tools

        reload(app.tools.aap_tools)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 1, "status": "running"}
        with patch.object(app.tools.aap_tools, "_get", return_value=mock_resp):
            result = app.tools.aap_tools.get_job_output(job_id=1)
        assert "error" in result
        assert "still running" in result["error"]
