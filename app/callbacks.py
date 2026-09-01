"""Safety callbacks for the migration agent.

Provides a before_tool_callback that enforces the dry-run guardrail on
destructive tools (create_migration_plan, execute_migration, rollback_migration).
The readiness gate (NOT READY check) is handled deterministically by the
graph readiness_router node.

All migration tool invocations are logged for audit purposes.
"""

import logging
import os

from google.adk.tools import BaseTool, ToolContext

log = logging.getLogger(__name__)

_DRY_RUN = os.environ.get("MIGRATION_DRY_RUN", "false").lower() == "true"

_DESTRUCTIVE_TOOLS = frozenset(
    {
        "create_migration_plan",
        "execute_migration",
        "rollback_migration",
    }
)


async def migration_safety_callback(
    tool: BaseTool,
    args: dict,
    tool_context: ToolContext,
) -> dict | None:
    """Intercept destructive migration tools with the dry-run gate."""
    if tool.name not in _DESTRUCTIVE_TOOLS:
        return None

    namespace = args.get("namespace", "")
    identifier = args.get("vm_name", "") or args.get("plan_name", "")

    if _DRY_RUN:
        log.warning(
            "[DRY-RUN] Blocked %s for %s/%s",
            tool.name,
            namespace,
            identifier,
        )
        return {
            "status": "dry_run",
            "tool": tool.name,
            "namespace": namespace,
            "identifier": identifier,
            "message": (
                f"Tool '{tool.name}' was NOT executed because MIGRATION_DRY_RUN "
                "is enabled. Disable dry-run mode to proceed."
            ),
        }

    log.info(
        "[APPROVED] %s for %s/%s -- proceeding",
        tool.name,
        namespace,
        identifier,
    )
    return None
