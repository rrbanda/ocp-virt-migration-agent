"""Multi-cluster Kubernetes client factory.

Builds separate ApiClient instances for the MTV management cluster and the
OCP Virtualization target cluster. When explicit URL + token env vars are
set, the client connects to a remote cluster. Otherwise it falls back to
in-cluster service account auth or local kubeconfig (backward-compatible).

Clients are lazily created and refreshed on each call to handle OCP token
expiry (tokens from ``oc login`` expire after 24 h).

Configuration via environment variables:

  MTV cluster (Forklift providers, plans, migrations, inventory Route):
    MTV_API_URL   - K8s API server URL. Empty = in-cluster / kubeconfig.
    MTV_API_TOKEN - Bearer token.       Empty = in-cluster SA token.
    MTV_API_CA    - Path to CA bundle.  Empty = skip TLS verification.

  OCP Virt cluster (KubeVirt VMs, pod logs):
    VIRT_API_URL   - K8s API server URL.  Empty = same as MTV client.
    VIRT_API_TOKEN - Bearer token.        Empty = same as MTV token.
    VIRT_API_CA    - Path to CA bundle.   Empty = skip TLS verification.

  MTV inventory (HTTP API served by the Forklift Route):
    MTV_INVENTORY_URL   - Direct URL. Empty = auto-discover from Route CR.
    MTV_INVENTORY_TOKEN - Bearer token. Empty = use MTV_API_TOKEN, then SA.

  Configurable defaults:
    DEFAULT_MTV_NAMESPACE     - Default: mtv-user1
    DEFAULT_VIRT_NAMESPACE    - Default: vmimported-user1
    MTV_OPERATOR_NAMESPACE    - Default: openshift-mtv
    MTV_INVENTORY_ROUTE_NAME  - Default: forklift-inventory
    TARGET_STORAGE_CLASS      - Default: ocs-external-storagecluster-ceph-rbd
"""

import logging
import os

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException  # noqa: F401 — re-exported

    K8S_AVAILABLE = True
except ImportError:
    client = None  # type: ignore[assignment]
    config = None  # type: ignore[assignment]
    ApiException = Exception  # type: ignore[misc,assignment]
    K8S_AVAILABLE = False

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment configuration (read once at module load)
# ---------------------------------------------------------------------------
MTV_API_URL = os.environ.get("MTV_API_URL", "")
MTV_API_CA = os.environ.get("MTV_API_CA", "")

VIRT_API_URL = os.environ.get("VIRT_API_URL", "")
VIRT_API_CA = os.environ.get("VIRT_API_CA", "")

MTV_INVENTORY_URL = os.environ.get("MTV_INVENTORY_URL", "")

DEFAULT_MTV_NAMESPACE = os.environ.get("DEFAULT_MTV_NAMESPACE", "mtv-user1")
DEFAULT_VIRT_NAMESPACE = os.environ.get("DEFAULT_VIRT_NAMESPACE", "vmimported-user1")
MTV_OPERATOR_NAMESPACE = os.environ.get("MTV_OPERATOR_NAMESPACE", "openshift-mtv")
MTV_INVENTORY_ROUTE_NAME = os.environ.get("MTV_INVENTORY_ROUTE_NAME", "forklift-inventory")
TARGET_STORAGE_CLASS = os.environ.get("TARGET_STORAGE_CLASS", "ocs-external-storagecluster-ceph-rbd")


# ---------------------------------------------------------------------------
# Token readers (re-read on every call to handle rotation/expiry)
# ---------------------------------------------------------------------------
def _read_token(env_var: str) -> str:
    """Read a bearer token from an env var, supporting file-path indirection."""
    val = os.environ.get(env_var, "")
    if val and os.path.isfile(val):
        with open(val) as f:
            return f.read().strip()
    return val


def _read_sa_token() -> str:
    """Read the in-cluster service account token (re-read each call)."""
    sa_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    if os.path.exists(sa_path):
        with open(sa_path) as f:
            return f.read().strip()
    return ""


# ---------------------------------------------------------------------------
# Client builder (fresh client each call — handles token refresh)
# ---------------------------------------------------------------------------
_incluster_loaded = False


def _ensure_default_config():
    """Load in-cluster or kubeconfig once (for fallback clients)."""
    global _incluster_loaded
    if _incluster_loaded or not K8S_AVAILABLE:
        return
    try:
        config.load_incluster_config()
    except config.ConfigException:
        try:
            config.load_kube_config()
        except config.ConfigException:
            pass
    _incluster_loaded = True


def _build_client(api_url: str, token: str, ca_path: str) -> "client.ApiClient | None":
    if not K8S_AVAILABLE:
        return None
    if api_url and token:
        conf = client.Configuration()
        conf.host = api_url.rstrip("/")
        conf.api_key = {"authorization": f"Bearer {token}"}
        conf.verify_ssl = bool(ca_path)
        if ca_path:
            conf.ssl_ca_cert = ca_path
        return client.ApiClient(configuration=conf)
    _ensure_default_config()
    return client.ApiClient()


# ---------------------------------------------------------------------------
# Lazy API handle factories (fresh token on each call)
# ---------------------------------------------------------------------------
def mtv_custom_api():
    """CustomObjectsApi targeting the MTV management cluster."""
    c = _build_client(MTV_API_URL, _read_token("MTV_API_TOKEN"), MTV_API_CA)
    return client.CustomObjectsApi(api_client=c) if c else None


def virt_custom_api():
    """CustomObjectsApi targeting the OCP Virt cluster."""
    url = VIRT_API_URL or MTV_API_URL
    token = _read_token("VIRT_API_TOKEN") or _read_token("MTV_API_TOKEN")
    ca = VIRT_API_CA or MTV_API_CA
    c = _build_client(url, token, ca)
    return client.CustomObjectsApi(api_client=c) if c else None


def virt_core_api():
    """CoreV1Api targeting the OCP Virt cluster (for pod logs)."""
    url = VIRT_API_URL or MTV_API_URL
    token = _read_token("VIRT_API_TOKEN") or _read_token("MTV_API_TOKEN")
    ca = VIRT_API_CA or MTV_API_CA
    c = _build_client(url, token, ca)
    return client.CoreV1Api(api_client=c) if c else None


def _get_inventory_token() -> str:
    """Resolve the bearer token for the Forklift inventory HTTP API.

    Priority: MTV_INVENTORY_TOKEN > MTV_API_TOKEN > in-cluster SA token.
    """
    for env_var in ("MTV_INVENTORY_TOKEN", "MTV_API_TOKEN"):
        t = _read_token(env_var)
        if t:
            return t
    return _read_sa_token()


# ---------------------------------------------------------------------------
# Startup log
# ---------------------------------------------------------------------------
if MTV_API_URL:
    log.info("MTV cluster: %s", MTV_API_URL)
else:
    log.info("MTV cluster: in-cluster / kubeconfig (default)")

if VIRT_API_URL:
    log.info("Virt cluster: %s", VIRT_API_URL)
elif MTV_API_URL:
    log.info("Virt cluster: same as MTV cluster")
else:
    log.info("Virt cluster: in-cluster / kubeconfig (default)")

if MTV_INVENTORY_URL:
    log.info("MTV inventory URL: %s (direct)", MTV_INVENTORY_URL)
else:
    log.info("MTV inventory URL: auto-discover from Route CR")
