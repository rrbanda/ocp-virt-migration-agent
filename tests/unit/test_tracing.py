"""Unit tests for the tracing module."""

import os
from unittest.mock import patch


class TestEnableTracing:

    @patch.dict(os.environ, {"MLFLOW_TRACKING_URI": ""}, clear=False)
    def test_noop_when_uri_not_set(self):
        from importlib import reload

        import app.tracing
        reload(app.tracing)
        assert app.tracing._TRACING_ENABLED is False

    @patch.dict(os.environ, {"MLFLOW_TRACKING_URI": "http://fake:5000"}, clear=False)
    def test_graceful_when_mlflow_missing(self):
        with patch.dict("sys.modules", {"mlflow": None}):
            from importlib import reload

            import app.tracing
            try:
                reload(app.tracing)
            except Exception:
                pass
            assert app.tracing._TRACING_ENABLED is False


class TestWrapToolWithTrace:

    def test_passthrough_when_tracing_disabled(self):
        from app.tracing import wrap_tool_with_trace

        def my_func(x: str) -> dict:
            return {"result": x}

        wrapped = wrap_tool_with_trace(my_func)
        assert wrapped("hello") == {"result": "hello"}

    def test_preserves_function_name(self):
        from app.tracing import wrap_tool_with_trace

        def my_tool(x: str) -> dict:
            return {"result": x}

        wrapped = wrap_tool_with_trace(my_tool, name="custom_name")
        assert wrapped("test") == {"result": "test"}
