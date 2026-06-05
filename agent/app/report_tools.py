"""Artifact-based report persistence for the migration agent.

Provides a FunctionTool that saves a migration report as a downloadable
artifact via the ADK artifact service. The report is accessible from the
ADK Web UI's artifact panel.
"""

from google.adk.tools import ToolContext
from google.genai import types


async def save_report_artifact(
    report_content: str, filename: str, tool_context: ToolContext
) -> dict:
    """Save a migration report as a downloadable artifact.

    The report is persisted via the ADK artifact service and can be
    downloaded from the ADK Web UI.

    Args:
        report_content: The full report text in Markdown format.
        filename: Filename for the artifact (e.g. 'migration-report.md').
        tool_context: Injected by ADK runtime -- do not pass manually.

    Returns:
        Dictionary with status, filename, and artifact version number.
    """
    artifact = types.Part.from_text(text=report_content)
    version = await tool_context.save_artifact(
        filename=filename, artifact=artifact
    )
    return {"status": "saved", "filename": filename, "version": version}
