"""Pytest configuration for ADK agent evaluations.

Shared fixtures for eval test files. Execute with::

    uv run pytest tests/eval/ -v
"""

import json
import pathlib

import pytest

EVAL_DIR = pathlib.Path(__file__).parent
EVAL_FILES = sorted(EVAL_DIR.glob("*.test.json"))


def load_eval_ids():
    """Yield (file_path, eval_case_id) pairs for parametrization."""
    for path in EVAL_FILES:
        data = json.loads(path.read_text())
        for case in data.get("eval_cases", []):
            yield pytest.param(path, case["eval_id"], id=f"{path.stem}::{case['eval_id']}")


@pytest.fixture(scope="session")
def agent_module():
    """Import the agent module (triggers skill discovery and agent build)."""
    from app import agent
    return agent
