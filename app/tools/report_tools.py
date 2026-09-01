"""Artifact-based report persistence for the migration agent.

Provides a FunctionTool that saves a migration report as a downloadable
artifact via the ADK artifact service. The report is accessible from the
ADK Web UI's artifact panel.
"""

import logging
import re

from google.adk.tools import ToolContext
from google.genai import types

log = logging.getLogger(__name__)

_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,254}$")


async def save_report_artifact(report_content: str, filename: str, tool_context: ToolContext) -> dict:
    """Save a migration report as a downloadable artifact.

    The report is persisted via the ADK artifact service and can be
    downloaded from the ADK Web UI.

    Args:
        report_content: The full report text in Markdown format.
        filename: Filename for the artifact (e.g. 'migration-report.md').

    Returns:
        Dictionary with status, filename, and artifact version number.
    """
    if not report_content or not report_content.strip():
        return {"status": "error", "message": "Report content is empty."}

    if not filename or not _SAFE_FILENAME.match(filename):
        return {
            "status": "error",
            "message": f"Invalid filename '{filename}'. Use alphanumeric characters, dots, hyphens, and underscores only.",
        }

    if ".." in filename or "/" in filename or "\\" in filename:
        return {"status": "error", "message": "Filename must not contain path separators."}

    try:
        artifact = types.Part.from_text(text=report_content)
        version = await tool_context.save_artifact(filename=filename, artifact=artifact)
        log.info("Report artifact saved: %s (version %s)", filename, version)
        return {"status": "saved", "filename": filename, "version": version}
    except Exception as e:
        log.error("Failed to save report artifact %s: %s", filename, e)
        return {"status": "error", "message": f"Failed to save artifact: {e!s}"}
