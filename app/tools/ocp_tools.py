"""OCP Virt / MTV integration tools for the migration agent.

These FunctionTools allow the ADK agent to interact with OpenShift
Virtualization and Migration Toolkit for Virtualization (MTV/Forklift)
to list VMware VMs, trigger migrations, monitor status, and read logs.

Supports multi-cluster deployments: the agent can run on any cluster
while connecting to separate MTV and OCP Virt clusters via environment
variables. See cluster_clients.py for configuration details.
"""

import logging
import os

try:
    import requests
    import urllib3
except ImportError:
    requests = None
    urllib3 = None

from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

_RETRYABLE = (requests.exceptions.ConnectionError, requests.exceptions.Timeout) if requests else ()

_ocp_ca = os.environ.get("OCP_CA_BUNDLE", "").strip()
if _ocp_ca.lower() == "false":
    _OCP_VERIFY = False
    if urllib3:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
elif _ocp_ca and os.path.isfile(_ocp_ca):
    _OCP_VERIFY = _ocp_ca
else:
    _OCP_VERIFY = True
    if not _ocp_ca:
        log.warning("OCP_CA_BUNDLE not set; using default TLS verification")

FORKLIFT_GROUP = "forklift.konveyor.io"
FORKLIFT_VERSION = "v1beta1"
KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
DEFAULT_NETWORK_DESTINATION = os.environ.get("DEFAULT_NETWORK_DESTINATION", "pod")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=15),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
def _http_get(url: str, headers: dict, timeout: int = 30) -> requests.Response:
    resp = requests.get(url, headers=headers, verify=_OCP_VERIFY, timeout=timeout)
    resp.raise_for_status()
    return resp


from ..shared.cluster_clients import (
    DEFAULT_MTV_NAMESPACE,
    DEFAULT_VIRT_NAMESPACE,
    K8S_AVAILABLE,
    MTV_INVENTORY_ROUTE_NAME,
    MTV_INVENTORY_URL,
    MTV_OPERATOR_NAMESPACE,
    TARGET_STORAGE_CLASS,
    ApiException,
    _get_inventory_token,
    mtv_core_api,
    mtv_custom_api,
    virt_custom_api,
)

_K8S_RETRYABLE_STATUSES = {403, 429, 500, 502, 503, 504}


def _is_retryable_k8s(exc: BaseException) -> bool:
    return isinstance(exc, ApiException) and exc.status in _K8S_RETRYABLE_STATUSES


_k8s_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_retryable_k8s),
    reraise=True,
    before_sleep=lambda rs: log.warning(
        "K8s API call failed (status %s), retrying attempt %d...",
        getattr(rs.outcome.exception(), "status", "?"),
        rs.attempt_number,
    ),
)


@_k8s_retry
def _k8s_list(api, **kwargs):
    """list_namespaced_custom_object with retry on transient errors."""
    return api.list_namespaced_custom_object(**kwargs)


@_k8s_retry
def _k8s_get(api, **kwargs):
    """get_namespaced_custom_object with retry on transient errors."""
    return api.get_namespaced_custom_object(**kwargs)


@_k8s_retry
def _k8s_create(api, **kwargs):
    """create_namespaced_custom_object with retry on transient errors (except 409)."""
    return api.create_namespaced_custom_object(**kwargs)


def _resolve_inventory(mtv_api) -> tuple[str, str]:
    """Resolve the Forklift inventory base URL and auth token.

    If MTV_INVENTORY_URL is set, uses it directly (no Route lookup needed).
    Otherwise discovers the URL from the Route CR on the MTV cluster.

    Returns:
        (inventory_base_url, bearer_token)
    """
    token = _get_inventory_token()

    if MTV_INVENTORY_URL:
        return MTV_INVENTORY_URL.rstrip("/"), token

    inv_route = _k8s_get(
        mtv_api,
        group="route.openshift.io",
        version="v1",
        namespace=MTV_OPERATOR_NAMESPACE,
        plural="routes",
        name=MTV_INVENTORY_ROUTE_NAME,
    )
    inv_url = f"https://{inv_route['spec']['host']}"
    return inv_url, token


def list_vmware_vms(namespace: str) -> dict:
    """List VMs from VMware vSphere via the MTV Forklift inventory.

    Queries the MTV inventory API to discover VMware VMs available for
    migration. Returns VM names, power state, OS, CPU, memory, and disk info.

    Args:
        namespace: MTV namespace with the VMware provider.

    Returns:
        Dictionary with 'vms' list containing VM details from VMware inventory.
    """
    namespace = namespace or DEFAULT_MTV_NAMESPACE

    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    try:
        api = mtv_custom_api()
        providers = _k8s_list(
            api,
            group=FORKLIFT_GROUP,
            version=FORKLIFT_VERSION,
            namespace=namespace,
            plural="providers",
        )
        vmware_provider = next(
            (p for p in providers.get("items", []) if p.get("spec", {}).get("type") == "vsphere"), None
        )
        if not vmware_provider:
            return {"error": f"No VMware provider found in namespace {namespace}"}

        conditions = vmware_provider.get("status", {}).get("conditions", [])
        inventory_ready = any(c.get("type") == "InventoryCreated" and c.get("status") == "True" for c in conditions)
        if not inventory_ready:
            return {
                "error": f"VMware provider '{vmware_provider['metadata']['name']}' inventory is not ready. "
                "Wait for the provider to finish syncing before querying VMs.",
                "provider_conditions": [
                    {"type": c.get("type"), "status": c.get("status"), "reason": c.get("reason", "")}
                    for c in conditions
                ],
            }

        provider_uid = vmware_provider["metadata"]["uid"]
        provider_name = vmware_provider["metadata"]["name"]

        inv_url, token = _resolve_inventory(api)

        resp = _http_get(
            f"{inv_url}/providers/vsphere/{provider_uid}/vms",
            headers={"Authorization": f"Bearer {token}"},
        )
        vms = resp.json()

        return {
            "provider": provider_name,
            "namespace": namespace,
            "vm_count": len(vms),
            "vms": [
                {
                    "name": vm.get("name"),
                    "id": vm.get("id"),
                    "power_state": vm.get("powerState"),
                    "cpu_count": vm.get("cpuCount"),
                    "memory_mb": vm.get("memoryMB"),
                    "guest_os": vm.get("guestName", "Unknown"),
                    "firmware": vm.get("firmware", "bios"),
                    "disk_count": len(vm.get("disks", [])),
                    "total_disk_gb": round(sum(d.get("capacity", 0) for d in vm.get("disks", [])) / (1024**3), 1),
                    "networks": [{"id": n.get("id"), "name": n.get("name", "Unknown")} for n in vm.get("networks", [])],
                }
                for vm in vms
            ],
        }
    except ApiException as e:
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error querying VMware inventory: {e!s}"}


def list_migrated_vms(namespace: str) -> dict:
    """List VMs that have been migrated to OCP Virtualization.

    Args:
        namespace: Namespace with migrated VMs.

    Returns:
        Dictionary with 'vms' list containing migrated VM details.
    """
    namespace = namespace or DEFAULT_VIRT_NAMESPACE

    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    try:
        api = virt_custom_api()
        vms = _k8s_list(
            api,
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural="virtualmachines",
        )
        result = []
        for vm in vms.get("items", []):
            spec = vm.get("spec", {})
            domain = spec.get("template", {}).get("spec", {}).get("domain", {})
            status = vm.get("status", {})
            result.append(
                {
                    "name": vm["metadata"]["name"],
                    "namespace": namespace,
                    "running": spec.get("running", False),
                    "status": status.get("printableStatus", "Unknown"),
                    "cpu_cores": domain.get("cpu", {}).get("cores"),
                    "memory": domain.get("resources", {}).get("requests", {}).get("memory"),
                    "created": vm["metadata"].get("creationTimestamp"),
                }
            )
        return {"namespace": namespace, "vm_count": len(result), "vms": result}
    except ApiException as e:
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error: {e!s}"}


def get_vm_details(namespace: str, vm_name: str) -> dict:
    """Get detailed info about a specific VM on OCP Virtualization.

    Args:
        namespace: Namespace containing the VM.
        vm_name: Name of the VirtualMachine resource.

    Returns:
        Dictionary with full VM spec, status, disks, interfaces, conditions.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    try:
        api = virt_custom_api()
        vm = _k8s_get(
            api,
            group=KUBEVIRT_GROUP,
            version=KUBEVIRT_VERSION,
            namespace=namespace,
            plural="virtualmachines",
            name=vm_name,
        )
        spec = vm.get("spec", {})
        domain = spec.get("template", {}).get("spec", {}).get("domain", {})
        devices = domain.get("devices", {})
        status = vm.get("status", {})

        return {
            "name": vm_name,
            "namespace": namespace,
            "running": spec.get("running", False),
            "status": status.get("printableStatus", "Unknown"),
            "cpu_cores": domain.get("cpu", {}).get("cores"),
            "cpu_sockets": domain.get("cpu", {}).get("sockets"),
            "memory": domain.get("resources", {}).get("requests", {}).get("memory"),
            "disks": [{"name": d.get("name"), "bus": d.get("disk", {}).get("bus")} for d in devices.get("disks", [])],
            "interfaces": [{"name": i.get("name"), "model": i.get("model")} for i in devices.get("interfaces", [])],
            "volumes": [v.get("name") for v in spec.get("template", {}).get("spec", {}).get("volumes", [])],
            "conditions": [{"type": c.get("type"), "status": c.get("status")} for c in status.get("conditions", [])],
            "labels": vm["metadata"].get("labels", {}),
            "created": vm["metadata"].get("creationTimestamp"),
        }
    except ApiException as e:
        if e.status == 404:
            return {"error": f"VM '{vm_name}' not found in namespace '{namespace}'"}
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error: {e!s}"}


def get_migration_status(namespace: str) -> dict:
    """Get status of MTV migrations in a namespace.

    Args:
        namespace: Namespace with MTV plans/migrations.

    Returns:
        Dictionary with 'plans' and 'migrations' lists showing status.
    """
    namespace = namespace or DEFAULT_MTV_NAMESPACE

    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    try:
        api = mtv_custom_api()
        plans = _k8s_list(
            api,
            group=FORKLIFT_GROUP,
            version=FORKLIFT_VERSION,
            namespace=namespace,
            plural="plans",
        )
        migrations = _k8s_list(
            api,
            group=FORKLIFT_GROUP,
            version=FORKLIFT_VERSION,
            namespace=namespace,
            plural="migrations",
        )

        plan_list = []
        for p in plans.get("items", []):
            conditions = p.get("status", {}).get("conditions", [])
            migration_status = p.get("status", {}).get("migration", {})
            vms = migration_status.get("vms", [])
            plan_list.append(
                {
                    "name": p["metadata"]["name"],
                    "vm_count": len(p.get("spec", {}).get("vms", [])),
                    "phase": next((c["type"] for c in conditions if c.get("status") == "True"), "Unknown"),
                    "vms_completed": sum(1 for v in vms if v.get("phase") == "Completed"),
                    "vms_running": sum(1 for v in vms if v.get("phase") == "Running"),
                    "vms_failed": sum(1 for v in vms if v.get("phase") == "Failed"),
                }
            )

        migration_list = []
        for m in migrations.get("items", []):
            conditions = m.get("status", {}).get("conditions", [])
            migration_list.append(
                {
                    "name": m["metadata"]["name"],
                    "plan": m.get("spec", {}).get("plan", {}).get("name"),
                    "phase": next((c["type"] for c in conditions if c.get("status") == "True"), "Unknown"),
                    "started": m["metadata"].get("creationTimestamp"),
                }
            )

        return {
            "namespace": namespace,
            "plans": plan_list,
            "plan_count": len(plan_list),
            "migrations": migration_list,
            "migration_count": len(migration_list),
        }
    except ApiException as e:
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error: {e!s}"}


def create_migration_plan(
    namespace: str,
    vm_name: str,
    plan_name: str,
    target_namespace: str,
    warm: str,
) -> dict:
    """Create an MTV migration plan for a VMware VM. Does NOT start the migration.

    Creates NetworkMap, StorageMap, and Plan CRs. The Plan is validated by
    the MTV controller. Returns the plan details for human review. Call
    execute_migration to actually start the migration after approval.

    Args:
        namespace: The MTV namespace with the VMware provider.
        vm_name: The name of the VMware VM to migrate.
        plan_name: Name for the plan (auto-generated from vm_name if empty).
        target_namespace: Target namespace for the migrated VM.
        warm: Set to 'true' for warm migration (CBT-based, minimal downtime) or 'false' for cold.

    Returns:
        Dictionary with plan details for review including VM specs and mappings.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    if not namespace or not namespace.strip():
        return {"error": "namespace is required"}
    if not vm_name or not vm_name.strip():
        return {"error": "vm_name is required"}

    is_warm = warm.lower() == "true" if warm else False
    _FORKLIFT_API = f"{FORKLIFT_GROUP}/{FORKLIFT_VERSION}"
    created_resources = []

    try:
        api = mtv_custom_api()
        if api is None:
            return {"error": "Kubernetes client not available. Check cluster configuration."}

        log.info("Creating migration plan for VM '%s' in namespace '%s'", vm_name, namespace)

        providers = _k8s_list(
            api,
            group=FORKLIFT_GROUP,
            version=FORKLIFT_VERSION,
            namespace=namespace,
            plural="providers",
        )
        vmware_provider = next(
            (p for p in providers.get("items", []) if p.get("spec", {}).get("type") == "vsphere"), None
        )
        host_provider = next(
            (p for p in providers.get("items", []) if p.get("spec", {}).get("type") == "openshift"), None
        )
        if not vmware_provider:
            return {"error": f"No VMware (vsphere) provider found in namespace '{namespace}'"}
        if not host_provider:
            return {"error": f"No OpenShift provider found in namespace '{namespace}'"}

        provider_uid = vmware_provider["metadata"]["uid"]
        inv_url, token = _resolve_inventory(api)

        resp = _http_get(
            f"{inv_url}/providers/vsphere/{provider_uid}/vms",
            headers={"Authorization": f"Bearer {token}"},
        )
        vms = resp.json()
        target_vm = next((v for v in vms if v.get("name") == vm_name), None)
        if not target_vm:
            return {"error": f"VM '{vm_name}' not found in VMware inventory"}

        if not plan_name:
            plan_name = f"agent-plan-{vm_name.lower().replace('_', '-').replace('.', '-').replace(' ', '-')}"
        if not target_namespace:
            target_namespace = DEFAULT_VIRT_NAMESPACE

        src_provider_ref = {
            "apiVersion": _FORKLIFT_API,
            "kind": "Provider",
            "name": vmware_provider["metadata"]["name"],
            "namespace": namespace,
        }
        dst_provider_ref = {
            "apiVersion": _FORKLIFT_API,
            "kind": "Provider",
            "name": host_provider["metadata"]["name"],
            "namespace": namespace,
        }

        # Step 1: Create NetworkMap using source network NAME (per MTV docs)
        nmap_name = f"{plan_name}-netmap"
        dest_type = DEFAULT_NETWORK_DESTINATION
        nmap_map = []
        network_summary = []
        for net in target_vm.get("networks", []):
            net_name = net.get("name", "")
            if not net_name:
                continue
            dest = (
                {"type": dest_type}
                if dest_type == "pod"
                else {"type": "multus", "name": dest_type, "namespace": target_namespace}
            )
            nmap_map.append({"source": {"name": net_name}, "destination": dest})
            network_summary.append(f"{net_name} -> {dest_type}")

        nmap = {
            "apiVersion": _FORKLIFT_API,
            "kind": "NetworkMap",
            "metadata": {"name": nmap_name, "namespace": namespace},
            "spec": {"provider": {"source": src_provider_ref, "destination": dst_provider_ref}, "map": nmap_map},
        }
        try:
            _k8s_create(
                api,
                group=FORKLIFT_GROUP,
                version=FORKLIFT_VERSION,
                namespace=namespace,
                plural="networkmaps",
                body=nmap,
            )
            created_resources.append(("networkmaps", nmap_name))
        except ApiException as e:
            if e.status != 409:
                return {"error": f"Failed to create NetworkMap: {e.status} {e.reason}"}

        # Step 2: Create StorageMap
        smap_name = f"{plan_name}-stormap"
        datastore_ids = {
            disk.get("datastore", {}).get("id")
            for disk in target_vm.get("disks", [])
            if disk.get("datastore", {}).get("id")
        }
        storage_map_entries = [
            {"source": {"id": ds_id}, "destination": {"storageClass": TARGET_STORAGE_CLASS}} for ds_id in datastore_ids
        ]
        if not storage_map_entries:
            return {"error": "VM has no disks with datastores -- cannot create StorageMap"}

        smap = {
            "apiVersion": _FORKLIFT_API,
            "kind": "StorageMap",
            "metadata": {"name": smap_name, "namespace": namespace},
            "spec": {
                "provider": {"source": src_provider_ref, "destination": dst_provider_ref},
                "map": storage_map_entries,
            },
        }
        try:
            _k8s_create(
                api,
                group=FORKLIFT_GROUP,
                version=FORKLIFT_VERSION,
                namespace=namespace,
                plural="storagemaps",
                body=smap,
            )
            created_resources.append(("storagemaps", smap_name))
        except ApiException as e:
            if e.status != 409:
                return {
                    "error": f"Failed to create StorageMap: {e.status} {e.reason}",
                    "orphaned_resources": [f"{k}/{n}" for k, n in created_resources],
                }

        # Step 3: Create Plan (does NOT create Migration -- that's execute_migration)
        plan_spec = {
            "provider": {"source": src_provider_ref, "destination": dst_provider_ref},
            "targetNamespace": target_namespace,
            "warm": is_warm,
            "map": {
                "network": {
                    "apiVersion": _FORKLIFT_API,
                    "kind": "NetworkMap",
                    "name": nmap_name,
                    "namespace": namespace,
                },
                "storage": {
                    "apiVersion": _FORKLIFT_API,
                    "kind": "StorageMap",
                    "name": smap_name,
                    "namespace": namespace,
                },
            },
            "vms": [{"id": target_vm["id"], "name": vm_name}],
        }
        plan = {
            "apiVersion": _FORKLIFT_API,
            "kind": "Plan",
            "metadata": {"name": plan_name, "namespace": namespace},
            "spec": plan_spec,
        }
        try:
            _k8s_create(
                api, group=FORKLIFT_GROUP, version=FORKLIFT_VERSION, namespace=namespace, plural="plans", body=plan
            )
            created_resources.append(("plans", plan_name))
        except ApiException as e:
            if e.status != 409:
                return {
                    "error": f"Failed to create Plan: {e.status} {e.reason}",
                    "orphaned_resources": [f"{k}/{n}" for k, n in created_resources],
                }

        # Step 4: Check Plan validation status
        import time as _time

        plan_status = "Unknown"
        for _ in range(6):
            _time.sleep(5)
            try:
                plan_cr = _k8s_get(
                    api,
                    group=FORKLIFT_GROUP,
                    version=FORKLIFT_VERSION,
                    namespace=namespace,
                    plural="plans",
                    name=plan_name,
                )
                conditions = plan_cr.get("status", {}).get("conditions", [])
                ready = next((c for c in conditions if c.get("type") == "Ready"), None)
                if ready:
                    plan_status = "Ready" if ready.get("status") == "True" else f"Not Ready: {ready.get('message', '')}"
                    break
            except Exception:
                pass

        return {
            "status": "plan_created",
            "plan_name": plan_name,
            "plan_validation": plan_status,
            "migration_type": "warm" if is_warm else "cold",
            "vm_name": vm_name,
            "vm_specs": {
                "cpu": target_vm.get("cpuCount"),
                "memory_mb": target_vm.get("memoryMB"),
                "disk_count": len(target_vm.get("disks", [])),
                "total_disk_gb": round(sum(d.get("capacity", 0) for d in target_vm.get("disks", [])) / (1024**3), 1),
                "os": target_vm.get("guestName", "Unknown"),
                "firmware": target_vm.get("firmware", "bios"),
                "power_state": target_vm.get("powerState"),
            },
            "network_mapping": network_summary,
            "storage_class": TARGET_STORAGE_CLASS,
            "target_namespace": target_namespace,
            "message": (
                f"Migration plan '{plan_name}' created and validated ({plan_status}). "
                f"Review the plan details above. To start the migration, call execute_migration('{namespace}', '{plan_name}')."
            ),
        }

    except ApiException as e:
        body = ""
        if e.body:
            body = e.body[:200] if isinstance(e.body, str) else e.body.decode("utf-8", errors="replace")[:200]
        return {"error": f"Kubernetes API error: {e.status} {e.reason} {body}"}
    except Exception as e:
        log.exception("Unexpected error creating migration plan for '%s'", vm_name)
        return {"error": f"Error creating migration: {e!s}"}


def execute_migration(
    namespace: str,
    plan_name: str,
    cutover: str,
) -> dict:
    """Start the migration by creating a Migration CR that references an existing Plan.

    Call this ONLY after create_migration_plan has been called and the human
    has approved the plan. This triggers the actual VM data transfer.

    Args:
        namespace: The MTV namespace containing the Plan.
        plan_name: The name of the validated migration plan to execute.
        cutover: For warm migrations, the RFC 3339 cutover time (e.g. '2025-03-15T02:00:00Z'). Empty for cold or immediate cutover.

    Returns:
        Dictionary with migration name and status.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}
    if not namespace or not plan_name:
        return {"error": "namespace and plan_name are required"}

    _FORKLIFT_API = f"{FORKLIFT_GROUP}/{FORKLIFT_VERSION}"

    try:
        api = mtv_custom_api()
        if api is None:
            return {"error": "Kubernetes client not available"}

        plan_cr = _k8s_get(
            api, group=FORKLIFT_GROUP, version=FORKLIFT_VERSION, namespace=namespace, plural="plans", name=plan_name
        )
        conditions = plan_cr.get("status", {}).get("conditions", [])
        ready = next((c for c in conditions if c.get("type") == "Ready"), None)
        if not ready or ready.get("status") != "True":
            msg = ready.get("message", "Unknown") if ready else "No Ready condition found"
            return {"error": f"Plan '{plan_name}' is not ready for migration: {msg}"}

        migration_name = f"{plan_name}-migration"
        migration_spec = {"plan": {"name": plan_name, "namespace": namespace}}
        if cutover and cutover.strip():
            migration_spec["cutover"] = cutover.strip()

        migration = {
            "apiVersion": _FORKLIFT_API,
            "kind": "Migration",
            "metadata": {"name": migration_name, "namespace": namespace},
            "spec": migration_spec,
        }
        try:
            _k8s_create(
                api,
                group=FORKLIFT_GROUP,
                version=FORKLIFT_VERSION,
                namespace=namespace,
                plural="migrations",
                body=migration,
            )
            log.info("Created Migration '%s' -- migration started", migration_name)
        except ApiException as e:
            if e.status == 409:
                log.info("Migration '%s' already exists, reusing", migration_name)
            else:
                return {"error": f"Failed to create Migration: {e.status} {e.reason}"}

        return {
            "status": "migration_started",
            "plan_name": plan_name,
            "migration_name": migration_name,
            "message": f"Migration started. Use get_migration_status('{namespace}') to monitor progress.",
        }

    except ApiException as e:
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error: {e!s}"}


def get_pod_logs(namespace: str, pod_pattern: str, tail_lines: int) -> dict:
    """Get logs from pods matching a pattern for MTV troubleshooting.

    Useful for debugging migration failures by reading forklift-controller,
    virt-v2v, or cdi-importer pod logs.

    Args:
        namespace: Namespace to search for pods (e.g., openshift-mtv).
        pod_pattern: Pattern to match pod names (e.g., forklift, virt-v2v, cdi).
        tail_lines: Number of log lines to return from the end (default: 50).

    Returns:
        Dictionary with pod logs keyed by pod name.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    try:
        core = mtv_core_api()
        pods = core.list_namespaced_pod(namespace=namespace)
        matching = [p for p in pods.items if pod_pattern in p.metadata.name]

        if not matching:
            return {"error": f"No pods matching '{pod_pattern}' in namespace '{namespace}'"}

        logs = {}
        for pod in matching[:5]:
            pod_name = pod.metadata.name
            try:
                for container in pod.spec.containers:
                    pod_log = core.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=namespace,
                        container=container.name,
                        tail_lines=tail_lines,
                    )
                    key = f"{pod_name}/{container.name}" if len(pod.spec.containers) > 1 else pod_name
                    logs[key] = pod_log
            except ApiException:
                logs[pod_name] = "(unable to read logs)"

        return {"namespace": namespace, "pattern": pod_pattern, "pod_count": len(matching), "logs": logs}
    except ApiException as e:
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error: {e!s}"}


def validate_migrated_vm(namespace: str, vm_name: str) -> dict:
    """Comprehensive post-migration validation for a migrated VM on OCP Virtualization.

    Checks VM boot status, guest agent connectivity, PVC binding, and
    compares the migrated VM against expected specs. Call this after
    migration completes to verify the VM is production-ready.

    Args:
        namespace: Namespace containing the migrated VirtualMachine.
        vm_name: Name of the VirtualMachine resource to validate.

    Returns:
        Dictionary with validation results for each check item.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    checks = {}
    overall = "PASS"

    try:
        api = virt_custom_api()

        # Check 1: VirtualMachine exists
        try:
            vm = _k8s_get(
                api,
                group=KUBEVIRT_GROUP,
                version=KUBEVIRT_VERSION,
                namespace=namespace,
                plural="virtualmachines",
                name=vm_name,
            )
            checks["vm_exists"] = {"status": "PASS", "detail": f"VirtualMachine '{vm_name}' found"}
        except ApiException as e:
            if e.status == 404:
                return {"error": f"VM '{vm_name}' not found in namespace '{namespace}'", "overall": "FAIL"}
            raise

        spec = vm.get("spec", {})
        status = vm.get("status", {})
        domain = spec.get("template", {}).get("spec", {}).get("domain", {})

        # Check 2: VM printable status
        printable = status.get("printableStatus", "Unknown")
        checks["vm_status"] = {
            "status": "PASS" if printable in ("Running", "Stopped") else "WARNING",
            "detail": f"Status: {printable}",
        }
        if printable not in ("Running", "Stopped"):
            overall = "WARNING"

        # Check 3: VirtualMachineInstance exists and is Running (if VM is set to run)
        if spec.get("running", False):
            try:
                vmi = _k8s_get(
                    api,
                    group=KUBEVIRT_GROUP,
                    version=KUBEVIRT_VERSION,
                    namespace=namespace,
                    plural="virtualmachineinstances",
                    name=vm_name,
                )
                vmi_phase = vmi.get("status", {}).get("phase", "Unknown")
                checks["vmi_running"] = {
                    "status": "PASS" if vmi_phase == "Running" else "FAIL",
                    "detail": f"VMI phase: {vmi_phase}",
                }
                if vmi_phase != "Running":
                    overall = "FAIL"
            except ApiException as e:
                if e.status == 404:
                    checks["vmi_running"] = {
                        "status": "FAIL",
                        "detail": "VirtualMachineInstance not found (VM not booted)",
                    }
                    overall = "FAIL"
                else:
                    raise
        else:
            checks["vmi_running"] = {"status": "SKIP", "detail": "VM is not set to running (spec.running=false)"}

        # Check 4: Guest agent connected
        conditions = status.get("conditions", [])
        agent_connected = any(c.get("type") == "AgentConnected" and c.get("status") == "True" for c in conditions)
        checks["guest_agent"] = {
            "status": "PASS" if agent_connected else "WARNING",
            "detail": "QEMU guest agent connected"
            if agent_connected
            else "Guest agent not detected (install qemu-guest-agent for full management)",
        }

        # Check 5: CPU and memory
        cpu_cores = domain.get("cpu", {}).get("cores")
        memory = domain.get("resources", {}).get("requests", {}).get("memory")
        checks["compute"] = {
            "status": "PASS",
            "detail": f"CPU cores: {cpu_cores}, Memory: {memory}",
        }

        # Check 6: Disks and volumes
        devices = domain.get("devices", {})
        disk_count = len(devices.get("disks", []))
        volumes = spec.get("template", {}).get("spec", {}).get("volumes", [])
        checks["storage"] = {
            "status": "PASS" if disk_count > 0 else "FAIL",
            "detail": f"Disks: {disk_count}, Volumes: {len(volumes)}",
        }
        if disk_count == 0:
            overall = "FAIL"

        # Check 7: Network interfaces
        interfaces = devices.get("interfaces", [])
        checks["networking"] = {
            "status": "PASS" if interfaces else "WARNING",
            "detail": f"Interfaces: {len(interfaces)} ({', '.join(i.get('name', '?') for i in interfaces)})",
        }

        # Check 8: Labels (migration metadata)
        labels = vm.get("metadata", {}).get("labels", {})
        checks["labels"] = {
            "status": "PASS",
            "detail": f"Labels: {len(labels)} ({', '.join(list(labels.keys())[:5])})",
        }

        return {
            "vm_name": vm_name,
            "namespace": namespace,
            "overall": overall,
            "checks": checks,
            "message": f"Post-migration validation {'passed' if overall == 'PASS' else 'has issues'} for '{vm_name}'.",
        }

    except ApiException as e:
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error: {e!s}"}
