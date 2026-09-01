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


def list_vmware_vms(namespace: str = "") -> dict:
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
                    "networks": [n.get("id") for n in vm.get("networks", [])],
                }
                for vm in vms
            ],
        }
    except ApiException as e:
        return {"error": f"Kubernetes API error: {e.status} {e.reason}"}
    except Exception as e:
        return {"error": f"Error querying VMware inventory: {e!s}"}


def list_migrated_vms(namespace: str = "") -> dict:
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


def get_migration_status(namespace: str = "") -> dict:
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
    plan_name: str = "",
    target_namespace: str = "",
) -> dict:
    """Create an MTV migration plan and trigger it for a VMware VM.

    Creates the required NetworkMap, StorageMap, Plan, and Migration CRs
    to migrate a VM from VMware to OCP Virtualization.

    IMPORTANT: This will START a real migration. The VM will be copied
    from VMware to OpenShift Virtualization.

    Args:
        namespace: The MTV namespace with the VMware provider.
        vm_name: The name of the VMware VM to migrate.
        plan_name: Optional name for the plan (auto-generated if empty).
        target_namespace: Target namespace for the migrated VM (uses DEFAULT_VIRT_NAMESPACE if empty).

    Returns:
        Dictionary with plan name, migration name, and status.
    """
    if not K8S_AVAILABLE:
        return {"error": "kubernetes Python client not installed"}

    if not namespace or not namespace.strip():
        return {"error": "namespace is required"}
    if not vm_name or not vm_name.strip():
        return {"error": "vm_name is required"}

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
            plan_name = f"agent-plan-{vm_name.lower().replace('_', '-')}"
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

        # Step 1: Create NetworkMap (maps all source NICs)
        nmap_name = f"{plan_name}-netmap"
        nmap_map = [
            {"source": {"id": net["id"]}, "destination": {"type": DEFAULT_NETWORK_DESTINATION}}
            for net in target_vm.get("networks", [])
            if net.get("id")
        ]

        nmap = {
            "apiVersion": _FORKLIFT_API,
            "kind": "NetworkMap",
            "metadata": {"name": nmap_name, "namespace": namespace},
            "spec": {
                "provider": {"source": src_provider_ref, "destination": dst_provider_ref},
                "map": nmap_map,
            },
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
            log.info("Created NetworkMap '%s' in '%s'", nmap_name, namespace)
        except ApiException as e:
            if e.status == 409:
                log.info("NetworkMap '%s' already exists in '%s', reusing", nmap_name, namespace)
            else:
                return {"error": f"Failed to create NetworkMap: {e.status} {e.reason}"}

        # Step 2: Create StorageMap
        smap_name = f"{plan_name}-stormap"
        datastore_ids = set()
        for disk in target_vm.get("disks", []):
            ds_id = disk.get("datastore", {}).get("id")
            if ds_id:
                datastore_ids.add(ds_id)

        storage_map_entries = [
            {"source": {"id": ds_id}, "destination": {"storageClass": TARGET_STORAGE_CLASS}} for ds_id in datastore_ids
        ]
        if not storage_map_entries:
            log.error("VM '%s' has no disks with datastores", vm_name)
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
            log.info("Created StorageMap '%s' in '%s'", smap_name, namespace)
        except ApiException as e:
            if e.status == 409:
                log.info("StorageMap '%s' already exists in '%s', reusing", smap_name, namespace)
            else:
                log.error(
                    "Failed to create StorageMap '%s': %s. Orphaned resources: %s",
                    smap_name,
                    e.reason,
                    created_resources,
                )
                return {
                    "error": f"Failed to create StorageMap: {e.status} {e.reason}",
                    "orphaned_resources": [f"{kind}/{name}" for kind, name in created_resources],
                }

        # Step 3: Create Plan
        plan_spec = {
            "provider": {"source": src_provider_ref, "destination": dst_provider_ref},
            "targetNamespace": target_namespace,
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
            "vms": [{"id": target_vm["id"]}],
        }

        plan = {
            "apiVersion": _FORKLIFT_API,
            "kind": "Plan",
            "metadata": {"name": plan_name, "namespace": namespace},
            "spec": plan_spec,
        }
        try:
            _k8s_create(
                api,
                group=FORKLIFT_GROUP,
                version=FORKLIFT_VERSION,
                namespace=namespace,
                plural="plans",
                body=plan,
            )
            created_resources.append(("plans", plan_name))
            log.info("Created Plan '%s' in '%s'", plan_name, namespace)
        except ApiException as e:
            if e.status == 409:
                log.info("Plan '%s' already exists in '%s', reusing", plan_name, namespace)
            else:
                log.error(
                    "Failed to create Plan '%s': %s. Orphaned resources: %s", plan_name, e.reason, created_resources
                )
                return {
                    "error": f"Failed to create Plan: {e.status} {e.reason}",
                    "orphaned_resources": [f"{kind}/{name}" for kind, name in created_resources],
                }

        # Step 4: Create Migration to trigger the plan
        migration_name = f"{plan_name}-migration"
        migration = {
            "apiVersion": _FORKLIFT_API,
            "kind": "Migration",
            "metadata": {"name": migration_name, "namespace": namespace},
            "spec": {
                "plan": {"name": plan_name, "namespace": namespace},
            },
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
            log.info("Created Migration '%s' in '%s' -- migration started", migration_name, namespace)
        except ApiException as e:
            if e.status == 409:
                log.info("Migration '%s' already exists in '%s'", migration_name, namespace)
            else:
                log.error(
                    "Failed to create Migration '%s': %s. Created resources: %s",
                    migration_name,
                    e.reason,
                    created_resources,
                )
                return {
                    "error": f"Failed to create Migration: {e.status} {e.reason}",
                    "created_resources": [f"{kind}/{name}" for kind, name in created_resources],
                }

        return {
            "status": "Migration triggered",
            "plan_name": plan_name,
            "migration_name": migration_name,
            "vm_name": vm_name,
            "target_namespace": target_namespace,
            "message": f"Migration of '{vm_name}' started. Use get_migration_status('{namespace}') to monitor progress.",
        }

    except ApiException as e:
        body = ""
        if e.body:
            body = e.body[:200] if isinstance(e.body, str) else e.body.decode("utf-8", errors="replace")[:200]
        log.error("Migration plan creation failed for '%s': %s %s %s", vm_name, e.status, e.reason, body)
        return {"error": f"Kubernetes API error: {e.status} {e.reason} {body}"}
    except Exception as e:
        log.exception("Unexpected error creating migration plan for '%s'", vm_name)
        return {"error": f"Error creating migration: {e!s}"}


def get_pod_logs(namespace: str, pod_pattern: str = "forklift", tail_lines: int = 50) -> dict:
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
