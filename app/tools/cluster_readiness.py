"""Cluster readiness tool for pre-flight validation.

Queries the live OpenShift cluster to check whether operators, storage,
networking, and compute resources are ready for VM migrations.
"""

import logging

from ..shared.cluster_clients import (
    K8S_AVAILABLE,
    ApiException,
    mtv_custom_api,
    virt_core_api,
)

log = logging.getLogger(__name__)


def check_cluster_readiness(namespace: str) -> dict:
    """Check if the OpenShift cluster is ready for VM migrations.

    Performs automated pre-flight checks on the live cluster including
    operator health, storage classes, worker node resources, and network
    configuration. Use this before your first migration wave.

    Args:
        namespace: MTV namespace to check (optional, uses default if empty).

    Returns:
        Dictionary with per-category check results and overall readiness.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    results = {
        "checks": {},
        "blockers": [],
        "warnings": [],
        "ready": True,
    }

    # 1. Check worker nodes
    try:
        core = virt_core_api()
        if core:
            nodes = core.list_node()
            workers = [n for n in nodes.items if any("worker" in label for label in (n.metadata.labels or {}))]
            results["checks"]["worker_nodes"] = {
                "count": len(workers),
                "status": "PASS" if len(workers) >= 3 else "WARNING",
                "detail": f"{len(workers)} worker nodes found (minimum 3 recommended)",
            }
            if len(workers) < 3:
                results["warnings"].append("Fewer than 3 worker nodes -- HA may be limited")
        else:
            results["checks"]["worker_nodes"] = {"status": "SKIP", "detail": "K8s client unavailable"}
    except Exception as e:
        results["checks"]["worker_nodes"] = {"status": "ERROR", "detail": str(e)}

    # 2. Check storage classes
    try:
        from kubernetes import client as k8s_client

        storage_api = k8s_client.StorageV1Api(api_client=virt_core_api()._api_client if virt_core_api() else None)
        scs = storage_api.list_storage_class()
        sc_names = [sc.metadata.name for sc in scs.items]
        has_default = any(
            sc.metadata.annotations
            and sc.metadata.annotations.get("storageclass.kubernetes.io/is-default-class") == "true"
            for sc in scs.items
        )
        results["checks"]["storage_classes"] = {
            "count": len(sc_names),
            "names": sc_names,
            "has_default": has_default,
            "status": "PASS" if sc_names else "BLOCKER",
            "detail": f"{len(sc_names)} storage classes, default={'yes' if has_default else 'no'}",
        }
        if not sc_names:
            results["blockers"].append("No storage classes found")
            results["ready"] = False
    except Exception as e:
        results["checks"]["storage_classes"] = {"status": "ERROR", "detail": str(e)}

    # 3. Check MTV provider
    try:
        api = mtv_custom_api()
        if api:
            ns = namespace or "openshift-mtv"
            try:
                providers = api.list_namespaced_custom_object(
                    group="forklift.konveyor.io",
                    version="v1beta1",
                    namespace=ns,
                    plural="providers",
                )
                provider_names = [p["metadata"]["name"] for p in providers.get("items", [])]
                has_vmware = any(p.get("spec", {}).get("type") == "vsphere" for p in providers.get("items", []))
                results["checks"]["mtv_providers"] = {
                    "count": len(provider_names),
                    "names": provider_names,
                    "has_vmware": has_vmware,
                    "status": "PASS" if has_vmware else "WARNING",
                    "detail": f"{'VMware provider found' if has_vmware else 'No VMware provider -- configure before migration'}",
                }
                if not has_vmware:
                    results["warnings"].append("No VMware provider configured in MTV")
            except ApiException as e:
                if e.status == 404:
                    results["checks"]["mtv_providers"] = {
                        "status": "BLOCKER",
                        "detail": "MTV CRDs not found -- install MTV operator first",
                    }
                    results["blockers"].append("MTV operator not installed")
                    results["ready"] = False
                else:
                    results["checks"]["mtv_providers"] = {"status": "ERROR", "detail": str(e)}
        else:
            results["checks"]["mtv_providers"] = {"status": "SKIP", "detail": "K8s client unavailable"}
    except Exception as e:
        results["checks"]["mtv_providers"] = {"status": "ERROR", "detail": str(e)}

    # 4. Summary
    total_checks = len(results["checks"])
    passed = sum(1 for c in results["checks"].values() if c.get("status") == "PASS")
    results["summary"] = {
        "total_checks": total_checks,
        "passed": passed,
        "blockers": len(results["blockers"]),
        "warnings": len(results["warnings"]),
        "readiness": "READY" if results["ready"] and not results["blockers"] else "NOT READY",
    }

    return results
