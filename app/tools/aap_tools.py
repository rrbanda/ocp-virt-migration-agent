"""AAP (Ansible Automation Platform) integration tools for the migration agent.

These FunctionTools allow the ADK agent to interact with AAP Controller
to trigger and monitor Ansible jobs programmatically.

Configuration via environment variables:
  AAP_URL        - AAP Controller/Gateway URL
  AAP_TOKEN      - AAP API Bearer token (from Secret -- never hardcode)
  AAP_API_PREFIX - API path prefix (default: /api/controller/v2)
  AAP_CA_BUNDLE  - Path to CA bundle for TLS verification (optional)

  PRE_MIGRATION_TEMPLATE_ID  - AAP template ID for pre-migration assessment
  POST_MIGRATION_TEMPLATE_ID - AAP template ID for post-migration validation
"""

import logging
import os

import requests
import urllib3
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)

AAP_URL = os.environ.get("AAP_URL", "")
AAP_TOKEN = os.environ.get("AAP_TOKEN", "")
AAP_API_PREFIX = os.environ.get("AAP_API_PREFIX", "/api/controller/v2")
AAP_CA_BUNDLE = os.environ.get("AAP_CA_BUNDLE", "").strip()

PRE_MIGRATION_TEMPLATE_ID = os.environ.get("PRE_MIGRATION_TEMPLATE_ID", "")
POST_MIGRATION_TEMPLATE_ID = os.environ.get("POST_MIGRATION_TEMPLATE_ID", "")

AAP_MAX_OUTPUT_BYTES = int(os.environ.get("AAP_MAX_OUTPUT_BYTES", str(512 * 1024)))

if AAP_CA_BUNDLE.lower() == "true":
    _VERIFY = True
elif AAP_CA_BUNDLE and os.path.isfile(AAP_CA_BUNDLE):
    _VERIFY = AAP_CA_BUNDLE
else:
    _VERIFY = False

_TERMINAL_STATUSES = ("successful", "failed", "error", "canceled")
_RETRYABLE = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {AAP_TOKEN}",
        "Content-Type": "application/json",
    }


def _api(path: str) -> str:
    base = AAP_URL.rstrip("/")
    prefix = AAP_API_PREFIX.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + prefix + path


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
def _get(url: str, timeout: int = 30) -> requests.Response:
    resp = requests.get(url, headers=_headers(), verify=_VERIFY, timeout=timeout)
    resp.raise_for_status()
    return resp


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
def _post(url: str, payload: dict, timeout: int = 30) -> requests.Response:
    resp = requests.post(url, headers=_headers(), json=payload, verify=_VERIFY, timeout=timeout)
    resp.raise_for_status()
    return resp


def list_job_templates() -> dict:
    """List available AAP job templates.

    Returns a list of job templates with their IDs, names, and descriptions.
    Use this to discover what automation jobs are available before launching one.

    Returns:
        Dictionary with 'templates' list, each containing id, name, description.
        Returns error message if AAP is not configured or unreachable.
    """
    if not AAP_URL or not AAP_TOKEN:
        return {"error": "AAP not configured. Set AAP_URL and AAP_TOKEN environment variables."}

    try:
        data = _get(_api("/job_templates/")).json()
        templates = []
        for jt in data.get("results", []):
            templates.append(
                {
                    "id": jt["id"],
                    "name": jt["name"],
                    "description": jt.get("description", ""),
                    "last_job_run": jt.get("last_job_run"),
                    "status": jt.get("status", "unknown"),
                }
            )
        return {"templates": templates, "count": len(templates)}
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to AAP at {AAP_URL}"}
    except requests.exceptions.HTTPError as e:
        return {"error": f"AAP API error: {e.response.status_code} {e.response.text[:200]}"}
    except Exception as e:
        log.exception("Unexpected error listing job templates")
        return {"error": f"Unexpected error: {e!s}"}


def launch_job(template_id: int, extra_vars: str) -> dict:
    """Launch an AAP job template and return the job ID.

    Triggers an Ansible job template on AAP Controller. The job runs
    asynchronously -- use get_job_status to check progress and
    get_job_output to retrieve results when complete.

    Args:
        template_id: The numeric ID of the job template to launch.
        extra_vars: JSON string of extra variables to pass to the job.
                    Example: '{"target_host": "hostname.example.com"}'

    Returns:
        Dictionary with 'job_id', 'status', and 'url' of the launched job.
        Returns error message if launch fails.
    """
    if not AAP_URL or not AAP_TOKEN:
        return {"error": "AAP not configured. Set AAP_URL and AAP_TOKEN environment variables."}

    try:
        payload = {}
        if extra_vars and extra_vars != "{}":
            payload["extra_vars"] = extra_vars

        data = _post(_api(f"/job_templates/{template_id}/launch/"), payload).json()
        log.info("Launched AAP job %s from template %s", data["id"], template_id)
        return {
            "job_id": data["id"],
            "status": data.get("status", "pending"),
            "url": _api(f"/jobs/{data['id']}/"),
            "message": f"Job {data['id']} launched successfully from template {template_id}",
        }
    except requests.exceptions.HTTPError as e:
        return {"error": f"Failed to launch job: {e.response.status_code} {e.response.text[:200]}"}
    except Exception as e:
        log.exception("Unexpected error launching job template %s", template_id)
        return {"error": f"Unexpected error: {e!s}"}


def get_job_status(job_id: int) -> dict:
    """Get the current status of an AAP job.

    Poll this endpoint to check if a launched job has completed.
    Terminal statuses are: successful, failed, error, canceled.
    Non-terminal statuses are: new, pending, waiting, running.

    Args:
        job_id: The numeric ID of the job to check.

    Returns:
        Dictionary with 'status', 'started', 'finished', 'elapsed' time,
        and 'failed' boolean. Returns error if job not found.
    """
    if not AAP_URL or not AAP_TOKEN:
        return {"error": "AAP not configured. Set AAP_URL and AAP_TOKEN environment variables."}

    try:
        data = _get(_api(f"/jobs/{job_id}/")).json()
        return {
            "job_id": data["id"],
            "status": data["status"],
            "started": data.get("started"),
            "finished": data.get("finished"),
            "elapsed": data.get("elapsed"),
            "failed": data.get("failed", False),
            "job_template_name": data.get("name", ""),
            "is_finished": data["status"] in _TERMINAL_STATUSES,
        }
    except requests.exceptions.HTTPError as e:
        return {"error": f"Failed to get job status: {e.response.status_code}"}
    except Exception as e:
        log.exception("Unexpected error getting job status %s", job_id)
        return {"error": f"Unexpected error: {e!s}"}


def get_job_output(job_id: int) -> dict:
    """Get the stdout output of a completed AAP job.

    Retrieves the full playbook output text from a finished job.
    Use this after get_job_status shows the job is complete.
    The output is the raw Ansible playbook log that can be analyzed
    by the ansible-output-parser skill.

    Args:
        job_id: The numeric ID of the completed job.

    Returns:
        Dictionary with 'output' containing the full playbook stdout text,
        and 'status' of the job. Returns error if job not found or still running.
    """
    if not AAP_URL or not AAP_TOKEN:
        return {"error": "AAP not configured. Set AAP_URL and AAP_TOKEN environment variables."}

    try:
        job_data = _get(_api(f"/jobs/{job_id}/")).json()

        if job_data["status"] not in _TERMINAL_STATUSES:
            return {
                "error": f"Job {job_id} is still {job_data['status']}. Wait for it to finish.",
                "status": job_data["status"],
            }

        output_resp = _get(_api(f"/jobs/{job_id}/stdout/?format=txt"), timeout=60)

        output_text = output_resp.text
        truncated = False
        if len(output_text) > AAP_MAX_OUTPUT_BYTES:
            output_text = output_text[:AAP_MAX_OUTPUT_BYTES]
            truncated = True
            log.warning(
                "Job %s output truncated from %d to %d bytes", job_id, len(output_resp.text), AAP_MAX_OUTPUT_BYTES
            )

        result = {
            "job_id": job_id,
            "status": job_data["status"],
            "output": output_text,
            "output_length": len(output_text),
        }
        if truncated:
            result["truncated"] = True
            result["original_length"] = len(output_resp.text)
        return result
    except requests.exceptions.HTTPError as e:
        return {"error": f"Failed to get job output: {e.response.status_code}"}
    except Exception as e:
        log.exception("Unexpected error getting job output %s", job_id)
        return {"error": f"Unexpected error: {e!s}"}
