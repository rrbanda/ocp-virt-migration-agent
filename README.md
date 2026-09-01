# ocp-virt-migration-agent

AI-powered VMware-to-OpenShift Virtualization migration agent built with [Google ADK](https://github.com/google/adk-python), deployed on OpenShift with OIDC auth, LLM flexibility, and configurable skills.

## What It Does

An intelligent migration coordinator that can:
- **Assess migration readiness** by analyzing Ansible playbook output (36 pre-migration checks)
- **Execute migrations** by triggering MTV (Migration Toolkit for Virtualization) plans
- **Monitor migrations** in real-time with log analysis and failure diagnosis
- **Validate post-migration** results (39 post-migration checks, before/after comparison)
- **Generate reports** with structured findings, blockers, and remediation steps
- **Plan migration batches** with capacity analysis and risk assessment

## Architecture

![Agent Pipeline](docs/images/02-agent-pipeline.png)

![Multi-Cluster Connectivity](docs/images/03-multi-cluster.png)

For detailed architecture documentation with 5 diagrams (deployment, agent pipeline, multi-cluster connectivity, tool/skill matrix, and data flow), see **[docs/architecture.md](docs/architecture.md)**.

### Multi-Agent Pipeline (AGENT_MODE=pipeline)

Architecture modeled after Google's official ADK 2.0 samples ([Ambient Expense Agent](https://github.com/google/adk-samples/tree/main/python/agents/ambient-expense-agent), [Small Business Loan Agent](https://github.com/google/adk-samples/tree/main/python/agents/small-business-loan-agent)).

```
MigrationWorkflow (ADK 2.0 Workflow graph)
  START -> Coordinator         -> all tools + skills, handles ~93% ad-hoc queries
        -> intent_router
             ├── "done"        -> END (Coordinator already answered)
             └── "pipeline"    -> PreMigrationAgent  (discover + assess + create plan)
                                    -> readiness_router
                                        ├── "ready"     -> HITL approval -> ExecutionAgent (execute + monitor)
                                        │                                      -> outcome_router
                                        │                                           ├── "terminal" -> PostMigrationAgent
                                        │                                           └── "running"  -> ExecutionAgent (loop)
                                        └── "not_ready" -> PostMigrationAgent (assessment report)
```

4 agents, each doing meaningful LLM work:

| Agent | Replaces | Model Tier | Purpose |
|---|---|---|---|
| **Coordinator** | Dispatcher + DoneAgent + BatchPlanner | reasoning | Ad-hoc queries, batch planning, pipeline dispatch |
| **PreMigrationAgent** | DiscoveryAgent + AssessmentAgent | reasoning | VM discovery, readiness assessment, plan creation |
| **ExecutionAgent** | MigrationAgent + StatusPoller | fast | Migration execution, status monitoring |
| **PostMigrationAgent** | ValidationAgent + RollbackAgent + ReporterAgent | reasoning | Validation, rollback, reporting |

ADK 2.0 features:
- **Workflow graph** -- deterministic edges with conditional routing and monitoring loop
- **HITL** -- `RequestInput` with durable pause/resume before destructive operations
- **FunctionTool confirmation** -- `require_confirmation=True` on destructive tools
- **before_tool_callback** -- dry-run gate on create_migration_plan, execute_migration, rollback_migration
- **RunConfig** -- max_llm_calls=200 safety limit, SSE streaming
- **Context compaction** -- older phases auto-summarized to reduce token cost
- **MLflow tracing** -- tool + LLM call spans for observability
- **Plugins** -- structured lifecycle logging across all agents and tools
- **ConfigMap-driven** -- agent instructions and model tiers managed via GitOps

### Single-pod Sidecar Pattern (OpenShift)

- `adk-web` container: nginx serving Angular UI + proxying `/api/` to localhost:8000
- `adk-api` container: `adk api_server` running the migration agent
- Init container: reconstructs skill directory tree from ConfigMap

## Skills

| Skill | Description |
|---|---|
| `pre-migration-analyzer` | 36 checks from customer's pre-migration playbook (hypervisor, OS, kernel, disk, packages, backup, CMDB) |
| `post-migration-validator` | 39 checks from customer's post-migration playbook (platform, ACM, vCenter cleanup, guest agent, CMDB) |
| `ansible-output-parser` | Parses AAP job output format (Slice headers, assertions, ignored errors, PLAY RECAP) |
| `assessment-report-generator` | Formal readiness report with per-check table, blockers, warnings, remediation |
| `completion-report-generator` | Migration completion report with before/after comparison and sign-off |
| `mtv-log-analyzer` | Diagnoses MTV 2.8–2.11 migration failures (cold, warm, live, storage copy offload) from forklift/virt-v2v/CDI logs |
| `migration-kb-builder` | Manages knowledge base of migration patterns and resolutions |
| `capacity-analyzer` | Cluster capacity analysis for migration planning |
| `batch-planner` | Groups VMs into migration batches by risk, dependency, and capacity |
| `risk-assessor` | Weighted risk scoring (OS, disk, network, criticality, backup, history) |
| `migration-workflow` | End-to-end orchestration: discover, assess, select migration type (cold/warm/live), migrate, monitor, validate, report |

Skills include bundled sample data from real customer playbook output for offline demos.

## Tools

| Tool | Source | Description |
|---|---|---|
| `list_vmware_vms` | MTV inventory API | Discover VMware VMs via Forklift provider |
| `list_migrated_vms` | KubeVirt API | List VMs on OCP Virtualization |
| `get_vm_details` | KubeVirt API | Detailed VM spec (CPU, memory, disks, interfaces) |
| `get_migration_status` | Forklift API | Check MTV plan/migration progress |
| `create_migration_plan` | Forklift API | Trigger a real VMware-to-OCP Virt migration |
| `get_pod_logs` | Kubernetes API | Read pod logs for troubleshooting |
| `list_job_templates` | AAP API | List available Ansible job templates |
| `launch_job` | AAP API | Trigger an Ansible playbook via AAP |
| `get_job_status` | AAP API | Poll Ansible job progress |
| `get_job_output` | AAP API | Retrieve playbook stdout output |
| `save_report_artifact` | ADK Artifacts | Save report as downloadable file |

## Pre-Built Images

| Image | Description |
|---|---|
| `quay.io/rbrhssa/adk-web:oidc` | ADK Web UI with OIDC auth support (nginx) |
| `quay.io/rbrhssa/adk-agent:migration` | Migration agent with all skills and sample data |

## Deployment Guide

### Step 1: Create namespace

```bash
oc new-project adk-web
```

### Step 2: Create image pull secret

Required if pulling from a private Quay registry:

```bash
oc create secret docker-registry quay-pull-secret \
  --docker-server=quay.io \
  --docker-username=YOUR_QUAY_USER \
  --docker-password=YOUR_QUAY_PASS \
  -n adk-web
```

### Step 3: Edit `deploy/openshift.yaml`

Replace these placeholders with your actual values:

| Placeholder | Where | Example Value |
|---|---|---|
| `LLM_API_BASE` | `OPENAI_API_BASE` env var (value becomes `https://YOUR_HOST/v1`) | `llamastack.example.com` |
| `ADK_MODEL_NAME` | `ADK_MODEL` env var | `openai/meta-llama/Llama-3.1-70B-Instruct` |
| `KEYCLOAK_HOST` | ConfigMap `adk-web-config` | `keycloak.example.com` (or see anonymous mode below) |
| `REALM_NAME` | ConfigMap `adk-web-config` | `my-realm` |
| `CLIENT_ID` | ConfigMap `adk-web-config` | `adk-web` |
| `mtv-user1` | `DEFAULT_MTV_NAMESPACE` | Your MTV provider namespace |
| `vmimported-user1` | `DEFAULT_VIRT_NAMESPACE` | Target namespace for migrated VMs |

Also set `TARGET_STORAGE_CLASS` to your cluster's storage class (e.g., `ocs-storagecluster-ceph-rbd`).

**Anonymous mode (no Keycloak):** Replace the `adk-web-config` ConfigMap data with:

```json
{
  "backendUrl": "/api"
}
```

### Step 4: Create Secrets (optional, per deployment mode)

**Single-cluster** (agent runs on the same cluster as MTV and OCP Virt):
No token Secrets needed -- the agent uses in-cluster service account auth. Skip this step.

**Multi-cluster** (agent, MTV, and OCP Virt on separate clusters):

```bash
# Get a token from the MTV cluster
oc --context=<MTV_CONTEXT> create token <SA_NAME> --duration=720h
oc create secret generic mtv-cluster-token --from-literal=token=<TOKEN> -n adk-web

# Get a token from the OCP Virt cluster (skip if same as MTV)
oc --context=<VIRT_CONTEXT> create token <SA_NAME> --duration=720h
oc create secret generic virt-cluster-token --from-literal=token=<TOKEN> -n adk-web
```

For multi-cluster, also set `MTV_API_URL` and `VIRT_API_URL` in the YAML to the remote API server URLs (e.g., `https://api.mtv-cluster.example.com:6443`).

**AAP integration** (optional):

```bash
oc create secret generic aap-agent-token --from-literal=token=<AAP_TOKEN> -n adk-web
```

Also set `AAP_URL` (e.g., `https://aap.example.com`) and optionally `PRE_MIGRATION_TEMPLATE_ID` / `POST_MIGRATION_TEMPLATE_ID` in the YAML.

### Step 5: Deploy

```bash
oc apply -f deploy/openshift.yaml -n adk-web
```

### Step 6: Verify

```bash
# Wait for pod to be ready (2/2 containers)
oc get pods -l app=adk-web -n adk-web -w

# Check API is responding
ROUTE=$(oc get route adk-web -n adk-web -o jsonpath='{.spec.host}')
curl -sk "https://${ROUTE}/api/version"
# Expected: {"version":"1.34.3","language":"python","language_version":"3.11.15"}

# Test VMware connectivity (if MTV is configured)
echo "https://${ROUTE}"
# Open in browser to access the chat UI
```

### Important: Skills Loading

The agent image has all 11 skills baked in at `/skills/`. However, the OpenShift deployment mounts an `emptyDir` volume at `/skills` (populated by the init container from the `adk-skills` ConfigMap). This means:

- **With the default ConfigMap**: Only `agent-instruction.md` is written to `/skills`. The 11 skill subdirectories from the image are hidden by the emptyDir mount. The agent will run but without skills.
- **To use baked-in skills**: Remove the `skills-dir` volume mount from the `adk-api` container and the `skills-raw` / `skills-dir` volumes from the pod spec. The agent will use skills directly from the image.
- **To use ConfigMap skills**: Add skill entries to the `adk-skills` ConfigMap using the `--` path separator convention (see Skills Guide below).

## Configuration

### Agent Environment Variables

| Env Var | Default | Description |
|---|---|---|
| `OPENAI_API_BASE` | - | LLM API endpoint |
| `ADK_MODEL` | `openai/gemini/models/gemini-2.5-flash` | LiteLlm model string |
| `AGENT_MODE` | `pipeline` | `pipeline` (graph workflow) or `single` (monolithic) |
| `SKILLS_DIR` | `/skills` | Skills directory path |
| `MAX_LLM_CALLS` | `200` | Maximum LLM calls per run (safety limit) |
| `MIGRATION_DRY_RUN` | `false` | Block real migrations when `true` |
| `DEFAULT_MTV_NAMESPACE` | `mtv-user1` | MTV provider namespace |
| `DEFAULT_VIRT_NAMESPACE` | `vmimported-user1` | Target namespace for migrated VMs |
| `AAP_URL` | - | AAP Controller URL |
| `AAP_TOKEN` | *(from Secret)* | AAP API bearer token |
| `PRE_MIGRATION_TEMPLATE_ID` | - | AAP template ID for pre-migration assessment |
| `POST_MIGRATION_TEMPLATE_ID` | - | AAP template ID for post-migration validation |

See `deploy/openshift.yaml` for the full list including multi-cluster configuration.

## Test Prompts

See [docs/test-prompts.md](docs/test-prompts.md) for categorized test prompts covering all four use cases:
1. Migration readiness assessment
2. Migration monitoring and troubleshooting
3. Post-migration validation
4. Migration planning and capacity insights

## Disconnected / Air-Gapped Deployment

This agent can run in a fully disconnected environment with no external internet access at runtime.

### Container Images to Mirror

Pull these images into your mirror registry before deployment:

| Image | Purpose |
|---|---|
| `quay.io/rbrhssa/adk-web:oidc` | Angular UI + nginx reverse proxy |
| `quay.io/rbrhssa/adk-agent:migration` | Agent with all skills and sample data baked in |
| `busybox` (as referenced in `openshift.yaml`; resolve to `docker.io/library/busybox` for mirroring) | Init container for skill directory setup |

If rebuilding the agent image locally, you also need `python:3.11-slim` as the base.

### Python Packages (for Local Builds Only)

Pre-download all packages and their transitive dependencies:

```bash
pip download -d ./wheels \
  "google-adk>=1.0.0,<2.0.0" litellm python-dotenv \
  requests kubernetes tenacity

# Transfer ./wheels to the disconnected build host, then:
pip install --no-cache-dir --no-index --find-links=./wheels \
  "google-adk>=1.0.0,<2.0.0" litellm python-dotenv \
  requests kubernetes tenacity
```

### LLM Requirement

The agent requires an **OpenAI-compatible LLM endpoint** reachable from the cluster. No external API calls are needed if you host the model locally:

| Option | Notes |
|---|---|
| **Ollama** | `OPENAI_API_BASE=http://ollama-svc:11434/v1` |
| **vLLM** | `OPENAI_API_BASE=http://vllm-svc:8000/v1` |
| **TGI** (Text Generation Inference) | `OPENAI_API_BASE=http://tgi-svc:8080/v1` |
| **Llama Stack** on OpenShift AI | `OPENAI_API_BASE=https://llamastack-svc/v1` |

Set `OPENAI_API_KEY=not-needed` for local models that don't require authentication.

### Cluster Prerequisites

| Requirement | Minimum Version | Purpose |
|---|---|---|
| **OpenShift** | 4.18+ | Container platform |
| **OCP Virtualization** | 4.18+ | Target platform for migrated VMs (4.21 for MIG vGPU, UDN, Lightspeed) |
| **Migration Toolkit for Virtualization (MTV)** | 2.10+ | VMware-to-OCP Virt migration engine (2.11 for storage copy offload, OVA import) |
| **VMware vSphere** | 6.5+ | Source hypervisor (configured as MTV provider); vSphere 7 EOL Oct 2025 |
| **Storage** | ODF or equivalent | StorageClass for VM disk PVCs |
| **Keycloak** (optional) | -- | OIDC authentication for the UI |
| **Ansible Automation Platform** (optional) | 2.4+ | Pre/post migration playbook execution |

### Network Requirements (Disconnected)

The agent pod requires network access only to internal services:

| Destination | Port | Purpose |
|---|---|---|
| MTV cluster API server | 6443 | Forklift provider/plan/migration CRs |
| OCP Virt cluster API server | 6443 | KubeVirt VM CRs, pod logs |
| LLM endpoint | varies | Model inference |
| AAP Controller (if used) | 443 | Ansible job execution |
| Mirror registry | 443/5000 | Image pulls |

No external internet access is required at runtime. All skills and sample data are baked into the agent container image.

## Building Images

The agent image uses Red Hat UBI9 Python 3.12 as the base for RHOAI compliance.

```bash
# Using Makefile (recommended)
make build     # builds the standard agent image
make push      # pushes to registry

# Or build manually
podman build --platform linux/amd64 -f deploy/Dockerfile.agent -t adk-agent:migration .
podman push quay.io/rbrhssa/adk-agent:migration

# OpenShell sandbox image (for network-isolated deployments)
make build-openshell
make push-openshell

# Redeploy (no image rebuild needed for skill-only changes via ConfigMap)
oc rollout restart deployment/adk-web -n adk-web
```

## Developer Workflow

A Makefile provides standardized development targets:

```bash
make help              # show all available targets
make init              # create .env from .env.example
make env               # create venv and install dependencies
make run               # start ADK api_server on port 8000
make run-api           # start OpenAI-compatible FastAPI on port 8080
make test              # run unit tests
make test-behavioral   # run behavioral tests against a deployed agent
make lint              # run ruff linter
make deploy            # apply OpenShift manifests
make deploy-openshell  # deploy in OpenShell sandbox
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

Agent code uses [google-adk](https://github.com/google/adk-python) (Apache 2.0).
UI uses [adk-web](https://github.com/google/adk-web) (Apache 2.0).
