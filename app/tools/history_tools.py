"""Migration history tools for session-scoped record keeping.

Provides tools to record and search past migration outcomes within
the current session state. Records persist for the duration of the
ADK session but are not shared across sessions.
"""

import json
import logging
from datetime import UTC, datetime

from google.adk.tools import ToolContext

log = logging.getLogger(__name__)


async def record_migration(
    vm_name: str,
    namespace: str,
    status: str,
    summary: str,
    tool_context: ToolContext,
) -> dict:
    """Record a completed migration for future reference within this session.

    Args:
        vm_name: Name of the migrated VM.
        namespace: Namespace the migration ran in.
        status: Final status (completed, failed, rolled_back).
        summary: Brief summary of the migration outcome.

    Returns:
        Confirmation that the record was saved.
    """
    record = {
        "type": "migration_record",
        "vm_name": vm_name,
        "namespace": namespace,
        "status": status,
        "summary": summary,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    tool_context.state[f"migration_history:{vm_name}"] = json.dumps(record)
    log.info("Recorded migration: %s/%s -> %s", namespace, vm_name, status)

    return {
        "status": "recorded",
        "vm_name": vm_name,
        "message": f"Migration record for '{vm_name}' saved to session state.",
    }


async def search_migration_history(
    query: str,
    tool_context: ToolContext,
) -> dict:
    """Search past migration records in the current session.

    Args:
        query: Search term (VM name, namespace, or status keyword).

    Returns:
        Dictionary with matching migration records.
    """
    matches = []
    query_lower = query.lower()

    for key, value in tool_context.state.items():
        if not key.startswith("migration_history:"):
            continue
        try:
            record = json.loads(value) if isinstance(value, str) else value
            searchable = json.dumps(record).lower()
            if query_lower in searchable:
                matches.append(record)
        except (json.JSONDecodeError, TypeError):
            continue

    return {
        "query": query,
        "count": len(matches),
        "records": matches,
        "message": f"Found {len(matches)} migration record(s) matching '{query}'.",
    }
