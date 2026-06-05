# Architecture

Detailed architecture documentation for the OCP Virt Migration Agent. Every diagram is traced from the actual source code. Each section includes a colorful reference image and an editable Mermaid diagram.

---

## 1. OpenShift Deployment Architecture

How the agent is deployed on OpenShift as a single pod with a sidecar pattern.

![Deployment Architecture](images/01-deployment-architecture.png)

**Source**: [`deploy/openshift.yaml`](../deploy/openshift.yaml), [`deploy/nginx.conf`](../deploy/nginx.conf), [`deploy/Dockerfile.agent`](../deploy/Dockerfile.agent)

The pod uses a **sidecar pattern** with two containers sharing `localhost`:

| Container | Image | Port | Role |
|---|---|---|---|
| `adk-web` | `quay.io/rbrhssa/adk-web:oidc` | 8080 | nginx serving Angular UI, proxying `/api/` to `localhost:8000` |
| `adk-api` | `quay.io/rbrhssa/adk-agent:migration` | 8000 | ADK API server running the migration agent |
| init: `setup-skills` | `busybox` | -- | Reconstructs skill directory tree from ConfigMap keys |

**Network path**: Route (TLS edge :443) -> Service `adk-web` (:8080) -> nginx -> `proxy_pass http://localhost:8000/`

Only port 8080 is on the Service and Route. The API on 8000 is internal to the pod.

**Volumes**:

| Volume Name | Type | Source | Mounted To | Purpose |
|---|---|---|---|---|
| `web-config` | ConfigMap | `adk-web-config` | nginx at `runtime-config.json` | UI config (backend URL, OIDC) |
| `skills-raw` | ConfigMap | `adk-skills` | init at `/skills-raw` | Agent instruction override |
| `skills-dir` | emptyDir | -- | init writes `/skills`, `adk-api` reads `/skills` | Skill directory |
| `artifact-storage` | PVC (1Gi) | `adk-artifacts` | `adk-api` at `/app/.adk` | Saved report artifacts |

**Secrets**:

| Secret | Env Var | Optional? | Purpose |
|---|---|---|---|
| `quay-pull-secret` | imagePullSecrets | No (required for image pull) | Pull container images from Quay |
| `mtv-cluster-token` | `MTV_API_TOKEN` | Yes | Authenticate to remote MTV cluster |
| `virt-cluster-token` | `VIRT_API_TOKEN` | Yes | Authenticate to remote OCP Virt cluster |
| `aap-agent-token` | `AAP_TOKEN` | Yes | Authenticate to AAP Controller |

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
graph LR
    subgraph ext [External]
        Browser
        Keycloak["Keycloak OIDC"]
    end

    subgraph ocp [OpenShift Cluster]
        Route["Route :443 TLS edge"] --> Service["Service adk-web :8080"]
        Service --> Pod

        subgraph Pod [Pod adk-web]
            Init["init: setup-skills"]
            Web["adk-web nginx :8080"]
            Api["adk-api ADK :8000"]
            Web -->|"proxy /api/ -> localhost:8000"| Api
        end

        subgraph volumes [Volumes]
            CM_Config["web-config: ConfigMap adk-web-config"]
            CM_Skills["skills-raw: ConfigMap adk-skills"]
            PVC["artifact-storage: PVC adk-artifacts 1Gi"]
            EmptyDir["skills-dir: emptyDir"]
        end

        CM_Skills --> Init
        Init --> EmptyDir
        EmptyDir --> Api
        CM_Config --> Web
        PVC --> Api
    end

    Browser --> Route
    Browser --> Keycloak
```

</details>

---

## 2. Multi-Agent Pipeline Architecture

The agent uses Google ADK's multi-agent framework with a 6-phase sequential pipeline.

![Agent Pipeline](images/02-agent-pipeline.png)

**Source**: [`agent/app/agent.py`](../agent/app/agent.py) `_build_pipeline_agent()` (lines 128-350)

When `AGENT_MODE=pipeline` (default), the root agent is a **coordinator** (`LlmAgent`) that delegates full migration workflows to a **`MigrationPipeline`** (`SequentialAgent`) containing 6 phases:

| Phase | Agent | Type | `output_key` | Tools |
|---|---|---|---|---|
| 1 | `DiscoveryAgent` | LlmAgent | `vm_inventory` | `list_vmware_vms` |
| 2 | `AssessmentAgent` | LlmAgent | `readiness_verdict` | `launch_job`, `get_job_status`, `get_job_output`, SkillToolset |
| 3 | `MigrationAgent` | LlmAgent | `migration_id` | `create_migration_plan` |
| 4 | `MigrationMonitor` | LoopAgent | -- | (contains StatusPoller + StatusChecker) |
| 4a | `StatusPoller` | LlmAgent | `migration_status` | `get_migration_status`, `get_pod_logs`, SkillToolset |
| 4b | `StatusChecker` | BaseAgent | -- | (deterministic: checks terminal keywords, escalates) |
| 5 | `ValidationAgent` | LlmAgent | `validation_result` | `list_migrated_vms`, `get_vm_details`, `launch_job`, `get_job_status`, `get_job_output`, SkillToolset |
| 6 | `ReporterAgent` | LlmAgent | `final_report` | `save_report_artifact`, SkillToolset |

The **coordinator** also has all tools directly for ad-hoc queries (list VMs, check status, etc.) without running the full pipeline.

When `AGENT_MODE=single`, a single monolithic `LlmAgent` with all tools replaces the pipeline.

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
graph TD
    Coordinator["migration_coordinator LlmAgent"]
    Coordinator --> Pipeline["MigrationPipeline SequentialAgent"]

    Pipeline --> Discovery["DiscoveryAgent output_key: vm_inventory"]
    Pipeline --> Assessment["AssessmentAgent output_key: readiness_verdict"]
    Pipeline --> Migration["MigrationAgent output_key: migration_id"]
    Pipeline --> Monitor["MigrationMonitor LoopAgent"]
    Pipeline --> Validation["ValidationAgent output_key: validation_result"]
    Pipeline --> Reporter["ReporterAgent output_key: final_report"]

    Monitor --> Poller["StatusPoller output_key: migration_status"]
    Monitor --> Checker["StatusChecker BaseAgent"]
```

</details>

---

## 3. Multi-Cluster Connectivity

The agent connects to up to 4 external systems, each with independent authentication.

![Multi-Cluster Connectivity](images/03-multi-cluster.png)

**Source**: [`agent/app/cluster_clients.py`](../agent/app/cluster_clients.py), [`agent/app/ocp_tools.py`](../agent/app/ocp_tools.py), [`agent/app/aap_tools.py`](../agent/app/aap_tools.py)

### Connection Details

| Target | Auth Env Vars | API | Used By |
|---|---|---|---|
| **MTV Cluster** | `MTV_API_URL` + `MTV_API_TOKEN` | Forklift `v1beta1` (providers, plans, migrations, networkmaps, storagemaps) + Inventory Route HTTP | `list_vmware_vms`, `get_migration_status`, `create_migration_plan` |
| **Virt Cluster** | `VIRT_API_URL` + `VIRT_API_TOKEN` (falls back to MTV) | KubeVirt `v1` (VirtualMachines) + CoreV1 (pod logs) | `list_migrated_vms`, `get_vm_details`, `get_pod_logs` |
| **AAP Controller** | `AAP_URL` + `AAP_TOKEN` | REST `/api/controller/v2/` (job_templates, jobs, stdout) | `list_job_templates`, `launch_job`, `get_job_status`, `get_job_output` |
| **LLM Endpoint** | `OPENAI_API_BASE` + `OPENAI_API_KEY` (consumed by LiteLLM, not in agent Python code) | OpenAI-compatible `/v1` | All LlmAgent instances via LiteLlm |

### Token Resolution

**MTV/Virt K8s API tokens** (`_read_token` in `cluster_clients.py`):

1. Read env var (e.g., `MTV_API_TOKEN`)
2. If the value is a file path (`os.path.isfile`), read the file contents instead
3. If no URL+token pair is configured, fall back to `load_incluster_config()` or `load_kube_config()`

**Forklift Inventory HTTP token** (`_get_inventory_token`):

1. Try `MTV_INVENTORY_TOKEN` env var (with file-path indirection)
2. Else try `MTV_API_TOKEN` env var (with file-path indirection)
3. Else fall back to in-cluster SA token at `/var/run/secrets/kubernetes.io/serviceaccount/token`

**AAP tokens** are read directly from the `AAP_TOKEN` env var (no file indirection, no SA fallback).

### TLS Verification

| Connection | CA Env Var | Default |
|---|---|---|
| MTV/Virt K8s API | `MTV_API_CA` / `VIRT_API_CA` | Skip verification if unset |
| Forklift Inventory HTTP | `OCP_CA_BUNDLE` | Skip verification if unset |
| AAP Controller | `AAP_CA_BUNDLE` | Skip verification if unset; `"true"` = use system CAs |

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
graph LR
    subgraph agent [Agent Pod]
        OCP["ocp_tools.py"]
        AAP["aap_tools.py"]
        LLM_Client["LiteLlm"]
        Clients["cluster_clients.py"]
        OCP --> Clients
    end

    subgraph mtv [MTV Cluster]
        ForkliftAPI["Forklift API v1beta1"]
        InvRoute["Inventory Route"]
    end

    subgraph virt [Virt Cluster]
        KubeVirt["KubeVirt API v1"]
        CoreAPI["CoreV1 Pod Logs"]
    end

    subgraph aap [AAP Controller]
        Templates["/api/controller/v2/job_templates/"]
        Jobs["/api/controller/v2/jobs/"]
    end

    subgraph llm [LLM Endpoint]
        LLM_API["OPENAI_API_BASE /v1"]
    end

    Clients -->|"MTV_API_URL + TOKEN"| ForkliftAPI
    Clients -->|"MTV_API_URL + TOKEN"| InvRoute
    Clients -->|"VIRT_API_URL + TOKEN"| KubeVirt
    Clients -->|"VIRT_API_URL + TOKEN"| CoreAPI
    AAP -->|"AAP_URL + TOKEN"| Templates
    AAP -->|"AAP_URL + TOKEN"| Jobs
    LLM_Client -->|"OPENAI_API_BASE"| LLM_API
```

</details>

---

## 4. Tool and Skill Access Matrix

Which tools and skills are available to each agent in the pipeline.

![Tool and Skill Access Matrix](images/04-tool-skill-map.png)

**Source**: [`agent/app/agent.py`](../agent/app/agent.py) tool lists per agent

| Agent | list_vmware_vms | list_migrated_vms | get_migration_status | get_vm_details | create_migration_plan | get_pod_logs | list_job_templates | launch_job | get_job_status | get_job_output | save_report_artifact | SkillToolset |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Coordinator** | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| DiscoveryAgent | Y | | | | | | | | | | | |
| AssessmentAgent | | | | | | | | Y | Y | Y | | Y |
| MigrationAgent | | | | | Y | | | | | | | |
| StatusPoller | | | Y | | | Y | | | | | | Y |
| ValidationAgent | | Y | | Y | | | | Y | Y | Y | | Y |
| ReporterAgent | | | | | | | | | | | Y | Y |

The **SkillToolset** gives access to all 11 skills via `list_skills`, `load_skill`, and `load_skill_resource`. Note: SkillToolset is only included when skills are discovered at startup (`skills = _discover_skills(SKILLS_DIR)` in `agent.py` line 105). If `/skills` is empty or missing, agents marked Y for SkillToolset will have no skill tools at runtime.

---

## 5. Data Flow Through the Pipeline

How session state accumulates as data flows through each phase.

![Data Flow](images/05-data-flow.png)

**Source**: `output_key=` on each agent in [`agent/app/agent.py`](../agent/app/agent.py)

Each phase writes its output to a session state key. Subsequent phases read from prior keys:

| Phase | Agent | Writes | Reads |
|---|---|---|---|
| 1 | DiscoveryAgent | `vm_inventory` | (user request) |
| 2 | AssessmentAgent | `readiness_verdict` | `vm_inventory` |
| 3 | MigrationAgent | `migration_id` | `readiness_verdict`, `vm_inventory` |
| 4 | StatusPoller (inside MigrationMonitor) | `migration_status` | `migration_id` |
| 5 | ValidationAgent | `validation_result` | `migration_status`, `vm_inventory` |
| 6 | ReporterAgent | `final_report` | all prior keys |

### Session State Key Payloads

| Key | Content |
|---|---|
| `vm_inventory` | JSON: VM names, CPU, memory, disk, OS, power state, firmware from VMware |
| `readiness_verdict` | READY / NOT READY / READY WITH WARNINGS + risk rating + blockers + warnings |
| `migration_id` | Plan name, migration name, target namespace |
| `migration_status` | Phase, VMs completed/running/failed, error details |
| `validation_result` | PASS/FAIL + before/after comparison (CPU, memory, network) |
| `final_report` | Markdown migration completion report (saved as artifact) |

<details>
<summary>Mermaid source (editable)</summary>

```mermaid
sequenceDiagram
    participant User
    participant Coordinator as migration_coordinator
    participant D as DiscoveryAgent
    participant A as AssessmentAgent
    participant M as MigrationAgent
    participant Mon as MigrationMonitor
    participant V as ValidationAgent
    participant R as ReporterAgent

    User->>Coordinator: Migrate VM X
    Coordinator->>D: Delegate to MigrationPipeline
    D->>D: list_vmware_vms()
    Note right of D: state.vm_inventory

    D->>A: next phase
    A->>A: launch_job() + parse output
    Note right of A: state.readiness_verdict

    A->>M: next phase
    M->>M: create_migration_plan()
    Note right of M: state.migration_id

    M->>Mon: next phase
    loop Until terminal
        Mon->>Mon: get_migration_status()
        Note right of Mon: state.migration_status
    end

    Mon->>V: next phase
    V->>V: list_migrated_vms() + get_vm_details()
    Note right of V: state.validation_result

    V->>R: next phase
    R->>R: save_report_artifact()
    Note right of R: state.final_report
    R->>User: Migration complete + report
```

</details>
