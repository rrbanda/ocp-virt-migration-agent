"""Rollback tools for cleaning up failed migration CRs.

When a migration fails, the rollback tool deletes the CRs created by
``create_migration_plan``: Migration, Plan, StorageMap, and NetworkMap.
"""

import logging

from ..shared.cluster_clients import K8S_AVAILABLE, ApiException, mtv_custom_api
from .ocp_tools import FORKLIFT_GROUP, FORKLIFT_VERSION

log = logging.getLogger(__name__)


def rollback_migration(namespace: str, plan_name: str) -> dict:
    """Delete migration CRs created by a failed migration plan.

    Removes the Migration, Plan, StorageMap, and NetworkMap CRs that were
    created for the given plan. Safe to call even if some CRs are already
    gone (404 errors are silently ignored).

    Args:
        namespace: The MTV namespace containing the migration resources.
        plan_name: The name of the migration plan to roll back.

    Returns:
        Dictionary with status and list of deleted/skipped resources.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    if not namespace or not namespace.strip():
        return {"error": "namespace is required"}
    if not plan_name or not plan_name.strip():
        return {"error": "plan_name is required"}

    api = mtv_custom_api()
    if api is None:
        return {"error": "Kubernetes client not available"}

    migration_name = f"{plan_name}-migration"
    nmap_name = f"{plan_name}-netmap"
    smap_name = f"{plan_name}-stormap"

    resources_to_delete = [
        ("migrations", migration_name),
        ("plans", plan_name),
        ("storagemaps", smap_name),
        ("networkmaps", nmap_name),
    ]

    deleted = []
    skipped = []
    errors = []

    for plural, name in resources_to_delete:
        try:
            api.delete_namespaced_custom_object(
                group=FORKLIFT_GROUP,
                version=FORKLIFT_VERSION,
                namespace=namespace,
                plural=plural,
                name=name,
            )
            deleted.append(f"{plural}/{name}")
            log.info("Rollback: deleted %s/%s in %s", plural, name, namespace)
        except ApiException as e:
            if e.status == 404:
                skipped.append(f"{plural}/{name}")
                log.info("Rollback: %s/%s not found (already cleaned up)", plural, name)
            else:
                errors.append(f"{plural}/{name}: {e.status} {e.reason}")
                log.error("Rollback: failed to delete %s/%s: %s", plural, name, e.reason)
        except Exception as e:
            errors.append(f"{plural}/{name}: {e!s}")

    status = "rolled_back" if not errors else "partial_rollback"
    return {
        "status": status,
        "plan_name": plan_name,
        "namespace": namespace,
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "message": f"Rollback {'complete' if not errors else 'partial'}: "
        f"{len(deleted)} deleted, {len(skipped)} already gone, {len(errors)} errors",
    }
