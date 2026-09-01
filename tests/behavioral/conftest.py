"""Fixtures for migration agent behavioral tests.

These tests hit the deployed agent's /chat/completions endpoint.
Set MIGRATION_AGENT_URL to target your deployment.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_golden(category: str | None = None) -> list[dict[str, Any]]:
    """Load golden queries, optionally filtered by category."""
    path = FIXTURES_DIR / "golden_queries.yaml"
    with open(path, encoding="utf-8") as f:
        queries = yaml.safe_load(f) or []
    if category:
        return [q for q in queries if q.get("category") == category]
    return queries


@pytest.fixture
def agent_url() -> str:
    return os.environ.get("MIGRATION_AGENT_URL", "http://localhost:8080")


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=60.0) as client:
        yield client


@pytest.fixture
def known_tools() -> list[str]:
    """All tools registered on the migration agent."""
    return [
        "list_vmware_vms",
        "list_migrated_vms",
        "get_migration_status",
        "get_vm_details",
        "create_migration_plan",
        "execute_migration",
        "validate_migrated_vm",
        "get_pod_logs",
        "check_cluster_readiness",
        "rollback_migration",
        "list_job_templates",
        "launch_job",
        "get_job_status",
        "get_job_output",
        "save_report_artifact",
        "record_migration",
        "search_migration_history",
        "list_skills",
        "load_skill",
        "load_skill_resource",
    ]


async def run_query(client: httpx.AsyncClient, url: str, query: str) -> dict[str, Any]:
    """Send a query to the agent's /chat/completions endpoint."""
    resp = await client.post(
        f"{url}/chat/completions",
        json={
            "messages": [{"role": "user", "content": query}],
            "stream": False,
        },
    )
    resp.raise_for_status()
    return resp.json()
