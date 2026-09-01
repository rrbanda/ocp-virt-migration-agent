"""Validate that each eval file has the required ADK schema fields."""

import json
import pathlib

import pytest

from .conftest import load_eval_ids


@pytest.mark.parametrize("eval_file,eval_case_id", list(load_eval_ids()))
def test_eval_case_schema(eval_file: pathlib.Path, eval_case_id: str):
    """Validate that each eval file has the required ADK schema fields."""
    data = json.loads(eval_file.read_text())
    assert "eval_set_id" in data, f"Missing eval_set_id in {eval_file.name}"
    assert "eval_cases" in data, f"Missing eval_cases in {eval_file.name}"

    case = next(c for c in data["eval_cases"] if c["eval_id"] == eval_case_id)
    assert "conversation" in case, f"Missing conversation in {eval_case_id}"

    for turn in case["conversation"]:
        assert "user_content" in turn, f"Missing user_content in turn of {eval_case_id}"
        assert "parts" in turn["user_content"], f"Missing parts in user_content of {eval_case_id}"
