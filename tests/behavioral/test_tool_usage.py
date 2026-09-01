"""Behavioral tests: tool selection accuracy for the migration agent.

Validates that the agent calls the correct tools for migration-domain
queries.  Primary signal is response content (since tool_calls are
internal to the ADK loop); secondary signal is the ``context`` field
when present.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import load_golden, run_query

pytestmark = [pytest.mark.behavioral, pytest.mark.asyncio]


def _queries_with_tools() -> list[dict[str, Any]]:
    return [q for q in load_golden() if q.get("expected_tools")]


def _greeting_queries() -> list[dict[str, Any]]:
    return load_golden("greeting")


def _adversarial_queries() -> list[dict[str, Any]]:
    return load_golden("adversarial")


@pytest.mark.parametrize(
    "golden",
    _queries_with_tools(),
    ids=lambda q: q["query"][:60],
)
async def test_tool_selection(http_client, agent_url, golden):
    """Correct tools should be invoked and response should contain expected elements."""
    result = await run_query(http_client, agent_url, golden["query"])

    assert result["choices"], "No choices in response"
    content = result["choices"][0]["message"]["content"]
    assert content, "Empty response content"

    expected_elements = golden.get("expected_elements", [])
    if expected_elements:
        text_lower = content.lower()
        found = [e for e in expected_elements if e.lower() in text_lower]
        assert found, (
            f"Response does not contain any of {expected_elements}. "
            f"Response (first 500 chars): {content[:500]}"
        )

    context = result.get("context", [])
    if context:
        tool_names = [
            tc["function"]["name"]
            for msg in context
            for tc in msg.get("tool_calls", [])
            if "function" in tc
        ]
        if tool_names:
            for expected in golden["expected_tools"]:
                assert expected in tool_names, (
                    f"Expected tool '{expected}' not called. Called: {tool_names}"
                )


@pytest.mark.parametrize("golden", _greeting_queries(), ids=lambda q: q["query"][:40])
async def test_greeting_no_tools(http_client, agent_url, golden):
    """Greetings should not trigger migration tools."""
    result = await run_query(http_client, agent_url, golden["query"])
    content = result["choices"][0]["message"]["content"].lower()
    assert "vm_count" not in content, "Greeting triggered VMware inventory"
    assert "migration triggered" not in content, "Greeting triggered migration"


@pytest.mark.parametrize("golden", _adversarial_queries(), ids=lambda q: q["query"][:40])
async def test_adversarial_resistance(http_client, agent_url, golden):
    """Adversarial prompts should not leak internal instructions."""
    result = await run_query(http_client, agent_url, golden["query"])
    content = result["choices"][0]["message"]["content"]
    for rejected in golden.get("rejected_elements", []):
        assert rejected not in content, (
            f"Response leaked internal content: '{rejected}' found in response"
        )
