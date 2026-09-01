"""MLflow tracing integration for the migration agent.

When ``MLFLOW_TRACKING_URI`` is set, enables:

1. ``mlflow.litellm.autolog()`` -- captures CHAT_MODEL spans for every LLM call
   made through LiteLLM by any ADK agent in the pipeline.
2. ``wrap_tool_with_trace(func)`` -- wraps a tool function with an MLflow TOOL
   span so that tool calls, arguments, and results appear in the trace.

When ``MLFLOW_TRACKING_URI`` is **not** set, all functions are no-ops and the
agent runs without any MLflow dependency.

Adapted from the Red Hat agentic-starter-kits ADK template pattern.
"""

import logging
import time
from collections.abc import Callable
from os import getenv
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

_TRACING_ENABLED: bool = False

log = logging.getLogger(__name__)


def _safe_uri(uri: str) -> str:
    """Strip credentials and query params from a URI for safe logging."""
    parts = urlsplit(uri)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _check_mlflow_health(tracking_uri: str, max_wait: int = 5) -> None:
    """Verify the MLflow server is reachable, retrying for *max_wait* seconds."""
    import requests

    url = f"{tracking_uri.rstrip('/')}/health"
    safe = _safe_uri(url)
    start = time.monotonic()

    while True:
        remaining = max_wait - (time.monotonic() - start)
        if remaining <= 0:
            raise RuntimeError(f"MLflow unreachable at {safe} after {max_wait}s")
        try:
            insecure = getenv("MLFLOW_TRACKING_INSECURE_TLS", "").lower() in ("true", "1", "yes")
            resp = requests.get(url, timeout=min(5, remaining), verify=not insecure)
            if resp.status_code == 200:
                log.info("[Tracing] MLflow health OK at %s", safe)
                return
            log.warning("[Tracing] MLflow returned %d at %s", resp.status_code, safe)
        except requests.exceptions.RequestException as exc:
            log.warning("[Tracing] MLflow connection failed at %s: %s", safe, exc)
        time.sleep(1)


def enable_tracing() -> None:
    """Enable MLflow tracing if ``MLFLOW_TRACKING_URI`` is set.

    Safe to call unconditionally at startup -- when the env var is absent
    or the server is unreachable, tracing is silently skipped.
    """
    global _TRACING_ENABLED

    tracking_uri: str | None = getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        log.info("[Tracing] MLFLOW_TRACKING_URI not set -- tracing disabled")
        return

    try:
        import mlflow
        import mlflow.litellm
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "MLFLOW_TRACKING_URI is set but mlflow is not installed. "
            "Install with: pip install 'mlflow>=3.10.0'"
        ) from exc

    try:
        timeout = int(getenv("MLFLOW_HEALTH_CHECK_TIMEOUT", "5"))
    except ValueError:
        timeout = 5

    try:
        _check_mlflow_health(tracking_uri, max_wait=timeout)
    except RuntimeError:
        log.warning(
            "[Tracing] MLflow unreachable at %s -- continuing without tracing",
            _safe_uri(tracking_uri),
        )
        return

    try:
        mlflow.set_tracking_uri(tracking_uri)
        experiment = getenv("MLFLOW_EXPERIMENT_NAME", "migration-agent")
        mlflow.set_experiment(experiment)
        mlflow.config.enable_async_logging()
        mlflow.litellm.autolog()

        _TRACING_ENABLED = True
        log.info(
            "[Tracing ENABLED] MLflow -> %s, experiment: %s",
            _safe_uri(tracking_uri), experiment,
        )
    except Exception as exc:
        log.warning("[Tracing] Failed to configure MLflow: %s", exc)


def wrap_tool_with_trace(
    func: Callable,
    span_type: Literal["tool", "agent"] = "tool",
    name: str | None = None,
) -> Callable:
    """Wrap *func* with an MLflow trace span if tracing is enabled.

    Returns the original function unchanged when tracing is off.
    """
    if not _TRACING_ENABLED:
        return func

    import mlflow
    from mlflow.entities import SpanType

    mlflow_type = SpanType.TOOL if span_type == "tool" else SpanType.AGENT
    return mlflow.trace(span_type=mlflow_type, name=name or func.__name__)(func)
