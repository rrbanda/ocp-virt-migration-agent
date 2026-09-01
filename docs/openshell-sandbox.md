# OpenShell Sandbox Deployment

Run the OCP Virt Migration Agent inside an [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) sandbox with policy-enforced network isolation and credential injection. This is the recommended deployment mode for production environments where the agent triggers real VMware migrations.

## Why Use a Sandbox?

The migration agent calls 4 external systems that can modify live infrastructure:

| System | Risk | Sandbox Benefit |
|--------|------|-----------------|
| MTV Cluster (K8s API :6443) | Creates Plan/Migration CRs | Egress policy limits to specific cluster |
| OCP Virt Cluster (K8s API :6443) | Reads VM specs, pod logs | Egress policy limits to specific cluster |
| AAP Controller (:443) | Triggers Ansible playbooks | Egress policy limits to AAP endpoint |
| LLM Endpoint | Model inference | Egress policy limits to LLM service |

Without a sandbox, a compromised agent (via prompt injection or supply chain attack) could exfiltrate data to arbitrary endpoints. The OpenShell L7 policy engine blocks all traffic not matching the egress rules.

## Prerequisites

- OpenShift cluster with [OpenShell gateway](https://github.com/NVIDIA/OpenShell) installed
- `openshell` CLI connected to the gateway
- Podman or Docker for image builds
- `oc` CLI authenticated to the cluster

## Step 1: Build the Sandbox Image

```bash
cd /path/to/gadk-rhoai

podman build --platform linux/amd64 \
  -f deploy/Containerfile.openshell \
  -t quay.io/<your-org>/adk-agent-sandbox:migration .

podman push quay.io/<your-org>/adk-agent-sandbox:migration
```

Or build in-cluster via OpenShift BuildConfig:

```bash
make build-openshell
```

## Step 2: Create the Sandbox

```bash
openshell sandbox create \
  --name migration-agent \
  --from quay.io/<your-org>/adk-agent-sandbox:migration \
  --forward 8080 \
  -e ADK_MODEL=openai/meta-llama/Llama-3.1-70B-Instruct \
  -e OPENAI_API_BASE=http://vllm-svc.my-ns.svc.cluster.local:8000/v1 \
  -e OPENAI_API_KEY=not-needed \
  -e AGENT_MODE=pipeline \
  -e SKILLS_DIR=/skills \
  -e MIGRATION_DRY_RUN=false \
  -- uvicorn app.api:app --host 0.0.0.0 --port 8080
```

Flags:

- `--forward 8080` -- SSH tunnel so `localhost:8080` reaches the agent
- `-e` -- environment variables injected via OpenShell providers (never on disk)
- `-- <command>` -- the process OpenShell's supervisor executes inside the sandbox

### Multi-Cluster Tokens

For multi-cluster deployments (MTV and Virt on separate clusters), pass the tokens:

```bash
  -e MTV_API_URL=https://api.mtv-cluster.example.com:6443 \
  -e MTV_API_TOKEN=<token> \
  -e VIRT_API_URL=https://api.virt-cluster.example.com:6443 \
  -e VIRT_API_TOKEN=<token> \
  -e AAP_URL=https://aap.example.com \
  -e AAP_TOKEN=<token>
```

### MLflow Tracing

```bash
  -e MLFLOW_TRACKING_URI=https://mlflow.redhat-ods-applications.svc.cluster.local:8443 \
  -e MLFLOW_EXPERIMENT_NAME=migration-agent \
  -e MLFLOW_WORKSPACE=adk-web
```

## Step 3: Apply Egress Policy

Create a policy file that restricts outbound traffic to only the required endpoints:

```yaml
# policy.yaml -- L7 egress rules for the migration agent
sandbox:
  network:
    egress:
      # LLM endpoint
      - host: "vllm-svc.my-ns.svc.cluster.local"
        port: 8000
        methods: ["POST"]
        paths:
          - "/v1/chat/completions"
          - "/v1/completions"

      # MTV cluster K8s API
      - host: "api.mtv-cluster.example.com"
        port: 6443

      # OCP Virt cluster K8s API (if separate from MTV)
      - host: "api.virt-cluster.example.com"
        port: 6443

      # AAP Controller (if configured)
      - host: "aap.example.com"
        port: 443

      # MLflow (if tracing enabled)
      - host: "mlflow.redhat-ods-applications.svc.cluster.local"
        port: 8443
```

Apply the policy:

```bash
openshell policy set migration-agent --policy policy.yaml --wait
```

## Step 4: Verify

```bash
# Health check
curl -s http://localhost:8080/health | python3 -m json.tool
# {"status": "healthy", "agent_initialized": true}

# Chat completion (sample data mode -- no live cluster needed)
curl -s -X POST http://localhost:8080/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Analyze the sample pre-migration output and produce a readiness report."}],"stream":false}' \
  | python3 -m json.tool

# Verify egress is blocked to unauthorized endpoints
curl -s http://localhost:8080/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What is the weather?"}],"stream":false}'
# Agent should respond without making external calls (no weather tool)
```

## Step 5: Run Behavioral Tests

```bash
MIGRATION_AGENT_URL=http://localhost:8080 \
  make test-behavioral
```

## Cleanup

```bash
openshell sandbox delete migration-agent
```

## Comparison: Standard vs Sandbox Deployment

| Aspect | Standard (OpenShift YAML) | OpenShell Sandbox |
|--------|--------------------------|-------------------|
| Base image | UBI9 Python 3.12 | Same |
| Network isolation | K8s NetworkPolicy (L3/L4) | OpenShell L7 policy engine |
| Credential injection | K8s Secrets / env vars | OpenShell providers (never on disk) |
| Process supervision | Container runtime PID 1 | OpenShell supervisor via SSH |
| Start command | Dockerfile CMD | Explicit `-- <command>` |
| Egress logging | None | OpenShell audits all connections |
| Migration safety | `before_tool_callback` + `require_confirmation` | Same + L7 egress blocking |
| Port | 8000 (ADK) + 8080 (nginx) | 8080 (FastAPI direct) |

## Notes

- The agent uses the OpenAI-compatible `/chat/completions` API (via `app.api:app`), not the ADK `api_server`. This is required because OpenShell's supervisor replaces CMD.
- `BASE_URL` / `OPENAI_API_BASE` must be reachable from within the sandbox. Use cluster-internal DNS.
- Build with `--platform linux/amd64` when targeting x86_64 clusters from Apple Silicon.
- For single-cluster mode (agent on same cluster as MTV/Virt), the sandbox needs egress to the local K8s API at `kubernetes.default.svc.cluster.local:443`.
