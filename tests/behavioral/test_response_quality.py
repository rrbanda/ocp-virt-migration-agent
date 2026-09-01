"""Behavioral tests: response quality for the migration agent.

Validates that the agent produces structured, domain-appropriate responses
for migration assessment and validation queries.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import load_golden, run_query

pytestmark = [pytest.mark.behavioral, pytest.mark.asyncio]


def _assessment_queries() -> list[dict[str, Any]]:
    return load_golden("assessment")


def _validation_queries() -> list[dict[str, Any]]:
    return load_golden("validation")


@pytest.mark.parametrize("golden", _assessment_queries(), ids=lambda q: q["query"][:60])
async def test_assessment_report_structure(http_client, agent_url, golden):
    """Assessment responses should contain structured readiness elements."""
    result = await run_query(http_client, agent_url, golden["query"])
    content = result["choices"][0]["message"]["content"]
    assert content, "Empty response"
    assert len(content) > 200, (
        f"Assessment response too short ({len(content)} chars) -- "
        "expected a structured report"
    )

    content_lower = content.lower()
    structural_markers = ["ready", "risk", "blocker", "warning", "recommendation"]
    found = [m for m in structural_markers if m in content_lower]
    assert len(found) >= 2, (
        f"Assessment response lacks structure. "
        f"Expected markers like {structural_markers}, found: {found}"
    )


@pytest.mark.parametrize("golden", _validation_queries(), ids=lambda q: q["query"][:60])
async def test_validation_report_structure(http_client, agent_url, golden):
    """Validation responses should contain structured post-migration checks."""
    result = await run_query(http_client, agent_url, golden["query"])
    content = result["choices"][0]["message"]["content"]
    assert content, "Empty response"
    assert len(content) > 200, (
        f"Validation response too short ({len(content)} chars) -- "
        "expected a structured report"
    )

    content_lower = content.lower()
    structural_markers = ["platform", "openshift virtualization", "validated", "pass", "fail"]
    found = [m for m in structural_markers if m in content_lower]
    assert len(found) >= 2, (
        f"Validation response lacks structure. "
        f"Expected markers like {structural_markers}, found: {found}"
    )


async def test_health_endpoint(http_client, agent_url):
    """The /health endpoint should return healthy status."""
    resp = await http_client.get(f"{agent_url}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["agent_initialized"] is True
