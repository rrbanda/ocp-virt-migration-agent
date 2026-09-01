"""Multi-cluster Kubernetes client factory.

Builds separate ApiClient instances for the MTV management cluster and the
OCP Virtualization target cluster. When explicit URL + token env vars are
set, the client connects to a remote cluster. Otherwise it falls back to
in-cluster service account auth or local kubeconfig (backward-compatible).

Clients are cached with a TTL to avoid connection pool leaks while still
handling token rotation. The in-cluster config's built-in refresh hook
re-reads the SA token from disk every 60 seconds.

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
import threading
import time

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException

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
        try:
            with open(val) as f:
                return f.read().strip()
        except OSError as e:
            log.warning("Failed to read token file %s for %s: %s", val, env_var, e)
            return ""
    return val


def _read_sa_token() -> str:
    """Read the in-cluster service account token (re-read each call)."""
    sa_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    if os.path.exists(sa_path):
        try:
            with open(sa_path) as f:
                return f.read().strip()
        except OSError as e:
            log.warning("Failed to read SA token: %s", e)
    return ""


# ---------------------------------------------------------------------------
# Client cache (avoids connection pool leaks from per-call client creation)
# ---------------------------------------------------------------------------
_CLIENT_TTL = 300  # seconds (5 minutes)
_client_cache: dict[str, tuple["client.ApiClient", float]] = {}
_client_lock = threading.Lock()
_incluster_loaded = False


def _ensure_default_config():
    """Load in-cluster or kubeconfig once (for fallback clients)."""
    global _incluster_loaded
    if _incluster_loaded or not K8S_AVAILABLE:
        return
    try:
        config.load_incluster_config()
        log.info("Loaded in-cluster Kubernetes config (SA token auto-refresh enabled)")
    except config.ConfigException:
        try:
            config.load_kube_config()
            log.info("Loaded kubeconfig from default location")
        except config.ConfigException:
            log.warning(
                "No Kubernetes config available (neither in-cluster nor kubeconfig). "
                "MTV/OCP tools will fail unless explicit API URLs and tokens are configured."
            )
    _incluster_loaded = True


def _build_client(api_url: str, token: str, ca_path: str) -> "client.ApiClient | None":
    """Build or return a cached Kubernetes ApiClient.

    Clients are cached by (api_url, ca_path) key with a TTL. Stale clients
    are closed before replacement to avoid urllib3 connection pool leaks.
    """
    if not K8S_AVAILABLE:
        return None

    cache_key = f"{api_url}|{ca_path}" if api_url else "default"

    with _client_lock:
        cached = _client_cache.get(cache_key)
        if cached:
            cached_client, created_at = cached
            if (time.monotonic() - created_at) < _CLIENT_TTL:
                log.debug("Reusing cached K8s client for %s", cache_key)
                return cached_client
            log.info("K8s client cache expired for %s, rebuilding", cache_key)
            try:
                cached_client.close()
            except Exception:
                pass

        new_client = _create_client(api_url, token, ca_path)
        if new_client:
            _client_cache[cache_key] = (new_client, time.monotonic())
        return new_client


def _create_client(api_url: str, token: str, ca_path: str) -> "client.ApiClient | None":
    """Create a new Kubernetes ApiClient (internal, called by _build_client)."""
    try:
        if api_url and token:
            conf = client.Configuration()
            conf.host = api_url.rstrip("/")
            conf.api_key = {"authorization": f"Bearer {token}"}
            conf.verify_ssl = bool(ca_path)
            if ca_path and os.path.isfile(ca_path):
                conf.ssl_ca_cert = ca_path
            log.info("Built K8s client for remote cluster %s (TLS verify=%s)", api_url, bool(ca_path))
            return client.ApiClient(configuration=conf)
        if api_url and not token:
            log.warning("API URL '%s' configured but no token provided; falling back to default config", api_url)
        _ensure_default_config()
        log.info("Built K8s client using default config (in-cluster / kubeconfig)")
        return client.ApiClient()
    except Exception as e:
        log.error("Failed to build Kubernetes client (url=%s): %s", api_url or "default", e)
        return None


# ---------------------------------------------------------------------------
# Lazy API handle factories (cached client + fresh token on each call)
# ---------------------------------------------------------------------------
def mtv_custom_api():
    """CustomObjectsApi targeting the MTV management cluster."""
    c = _build_client(MTV_API_URL, _read_token("MTV_API_TOKEN"), MTV_API_CA)
    return client.CustomObjectsApi(api_client=c) if c else None


def mtv_core_api():
    """CoreV1Api targeting the MTV management cluster (for pod logs)."""
    c = _build_client(MTV_API_URL, _read_token("MTV_API_TOKEN"), MTV_API_CA)
    return client.CoreV1Api(api_client=c) if c else None


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
if K8S_AVAILABLE:
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
else:
    log.warning("kubernetes Python client not installed; MTV/OCP tools disabled")
