# EvalHub Integration Guide

How to evaluate the OCP Virt Migration Agent using RHOAI 3.5 EvalHub and MLflow.

## Prerequisites

- RHOAI 3.5 cluster with EvalHub and MLflow enabled
- The migration agent deployed (see main README)
- `oc` CLI authenticated to the cluster

## Architecture

```
Agent Pod (adk-api)
  |-- MLflow TOOL spans (per tool call)
  |-- MLflow CHAT_MODEL spans (per LLM call via LiteLLM autolog)
  |
  v
MLflow Server (redhat-ods-applications)
  |-- Experiment: "migration-agent"
  |-- Runs with tool traces + token usage
  |
  v
EvalHub API (/api/v1/evaluations/)
  |-- Submits eval jobs
  |-- CLEAR adapter reads traces from MLflow
  |-- Results logged back to MLflow
```

## Step 1: Enable MLflow Tracing on the Agent

Set these env vars on the `adk-api` container in your deployment:

```yaml
- name: MLFLOW_TRACKING_URI
  value: "https://mlflow.redhat-ods-applications.svc.cluster.local:8443"
- name: MLFLOW_EXPERIMENT_NAME
  value: "migration-agent"
- name: MLFLOW_WORKSPACE
  value: "<your-agent-namespace>"
- name: MLFLOW_TRACKING_INSECURE_TLS
  value: "false"
```

Install the tracing extra in the agent image (already included if using `Dockerfile.agent`):

```bash
pip install "gadk-rhoai-agent[tracing]"
```

Verify tracing is active by checking agent logs:

```bash
oc logs deploy/adk-web -c adk-api | grep "\[Tracing"
# Expected: [Tracing ENABLED] MLflow -> https://mlflow..., experiment: migration-agent
```

## Step 2: View Traces in MLflow

Access the RHOAI Dashboard:

```
https://rhods-dashboard-redhat-ods-applications.apps.<cluster-domain>
```

Navigate to **Experiments > migration-agent** to see traces. Each user interaction creates a run with:

- `CHAT_MODEL` spans for every LLM call
- `TOOL` spans for every tool invocation (with arguments and results)
- Token usage metrics

## Step 3: Run Behavioral Tests with MLflow Enrichment

The behavioral tests can use MLflow to extract tool call details:

```bash
MIGRATION_AGENT_URL=https://<agent-route> \
MLFLOW_TRACKING_URI=https://mlflow.redhat-ods-applications.svc.cluster.local:8443 \
MLFLOW_EXPERIMENT_NAME=migration-agent \
MLFLOW_TRACKING_TOKEN=$(oc whoami -t) \
  uv run pytest tests/behavioral/ -v
```

## Step 4: Submit an EvalHub Evaluation Job

### Using the EvalHub API

```bash
TOKEN=$(oc whoami -t)
EVALHUB=https://evalhub-redhat-ods-applications.apps.<cluster-domain>
NAMESPACE=<your-namespace>

curl -sk -X POST "${EVALHUB}/api/v1/evaluations/jobs" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Tenant: ${NAMESPACE}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "migration-agent-eval",
    "description": "Evaluate the VMware-to-OCP Virt migration agent",
    "model": {
      "url": "https://<agent-route>/chat/completions",
      "name": "migration-coordinator"
    },
    "benchmarks": [
      {
        "id": "arc_easy",
        "provider_id": "lm_evaluation_harness"
      }
    ],
    "experiment": {
      "name": "migration-agent-eval",
      "tags": [
        {"key": "agent", "value": "gadk-rhoai"},
        {"key": "environment", "value": "sandbox"}
      ]
    }
  }'
```

### Using the EvalHub SDK (from a notebook)

```python
from evalhub import EvalHubClient

client = EvalHubClient(
    base_url="https://evalhub-redhat-ods-applications.apps.<cluster-domain>",
    token="<oc-token>",
    namespace="<your-namespace>",
)

job = client.submit(
    name="migration-agent-eval",
    model_url="https://<agent-route>/chat/completions",
    model_name="migration-coordinator",
    benchmarks=[{"id": "arc_easy", "provider_id": "lm_evaluation_harness"}],
    experiment_name="migration-agent-eval",
)
print(f"Job submitted: {job.id}")
```

## Step 5: View Results

Results are logged to the MLflow experiment specified in the job. View them in the RHOAI Dashboard under **Experiments > migration-agent-eval**.

### Monitor job status

```bash
curl -sk "${EVALHUB}/api/v1/evaluations/jobs/${JOB_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "X-Tenant: ${NAMESPACE}"
```

## Available EvalHub Providers

| Provider | Description | Use For |
|----------|-------------|---------|
| `lm_evaluation_harness` | 180+ LLM benchmarks | Model quality baselines |
| `garak` | AI security scanning | Vulnerability assessment |
| `ibm-clear` (if enabled) | Agent trace evaluation | Tool trajectory analysis |
| `deepeval` (if enabled) | Agent behavioral eval | Response quality scoring |
| `ragas` (if enabled) | RAG evaluation | Knowledge retrieval accuracy |

## EvalHub API Reference

All endpoints use the base path `/api/v1/evaluations/` and require:
- `Authorization: Bearer <token>` header
- `X-Tenant: <namespace>` header for RBAC

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/evaluations/providers` | GET | List available evaluation providers |
| `/api/v1/evaluations/collections` | GET | List benchmark collections |
| `/api/v1/evaluations/jobs` | POST | Submit an evaluation job |
| `/api/v1/evaluations/jobs` | GET | List evaluation jobs |
| `/api/v1/evaluations/jobs/{id}` | GET | Get job status and results |
| `/api/v1/health` | GET | EvalHub health check |

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `MLFLOW_TRACKING_URI` | MLflow server URL (cluster-internal) | `https://mlflow.redhat-ods-applications.svc.cluster.local:8443` |
| `MLFLOW_EXPERIMENT_NAME` | Experiment name for traces | `migration-agent` |
| `MLFLOW_WORKSPACE` | RHOAI namespace for multi-tenant auth | `adk-web` |
| `MLFLOW_TRACKING_TOKEN` | Bearer token (from SA or `oc whoami -t`) | |
| `MLFLOW_TRACKING_INSECURE_TLS` | Skip TLS verification | `false` |
| `MLFLOW_HEALTH_CHECK_TIMEOUT` | Seconds to wait for MLflow at startup | `5` |
