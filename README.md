# gadk-rhoai

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

```
Browser --> OIDC (Keycloak) --> ADK Web UI (nginx) --> ADK API Server --> LLM
                                                            |
                                              +-------------+-------------+
                                              |             |             |
                                        MTV/OCP Virt    AAP/Ansible   Skills
                                        (VMware VMs,    (Pre/Post     (10 analysis
                                         migrations,    migration      skills with
                                         pod logs)      playbooks)     reference data)
```

### Multi-Agent Pipeline (AGENT_MODE=pipeline)

```
Coordinator (root_agent)
  |-- MigrationPipeline (SequentialAgent)
  |     |-- DiscoveryAgent      -> list VMware VMs
  |     |-- AssessmentAgent     -> run pre-migration checks, produce readiness report
  |     |-- MigrationAgent      -> trigger MTV migration
  |     |-- MigrationMonitor    -> poll status until complete (LoopAgent)
  |     |-- ValidationAgent     -> run post-migration checks, compare before/after
  |     |-- ReporterAgent       -> generate completion report
  |-- (direct tools for ad-hoc queries)
```

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
| `mtv-log-analyzer` | Diagnoses MTV migration failures from forklift/virt-v2v/CDI logs |
| `migration-kb-builder` | Manages knowledge base of migration patterns and resolutions |
| `capacity-analyzer` | Cluster capacity analysis for migration planning |
| `batch-planner` | Groups VMs into migration batches by risk, dependency, and capacity |
| `risk-assessor` | Weighted risk scoring (OS, disk, network, criticality, backup, history) |
| `migration-workflow` | End-to-end orchestration: discover, assess, migrate, monitor, validate, report |

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

## Quick Start

```bash
# 1. Create namespace
oc new-project adk-web

# 2. Create image pull secret (if images are private)
oc create secret docker-registry quay-pull-secret \
  --docker-server=quay.io \
  --docker-username=YOUR_QUAY_USER \
  --docker-password=YOUR_QUAY_PASS

# 3. Create cluster access tokens (for multi-cluster)
oc create secret generic mtv-cluster-token --from-literal=token=<MTV_TOKEN> -n adk-web
oc create secret generic virt-cluster-token --from-literal=token=<VIRT_TOKEN> -n adk-web
oc create secret generic aap-agent-token --from-literal=token=<AAP_TOKEN> -n adk-web

# 4. Edit deploy/openshift.yaml -- replace placeholders:
#    KEYCLOAK_HOST, REALM_NAME, CLIENT_ID
#    LLM_API_BASE, ADK_MODEL_NAME

# 5. Deploy
oc apply -f deploy/openshift.yaml

# 6. Get the URL
oc get route adk-web -o jsonpath='{.spec.host}'
```

## Configuration

### Agent Environment Variables

| Env Var | Default | Description |
|---|---|---|
| `OPENAI_API_BASE` | - | LLM API endpoint |
| `ADK_MODEL` | `openai/gemini/models/gemini-2.5-flash` | LiteLlm model string |
| `AGENT_MODE` | `pipeline` | `pipeline` (multi-agent) or `single` (monolithic) |
| `SKILLS_DIR` | `/skills` | Skills directory path |
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

## Building Images

```bash
# Build the agent image
cd /path/to/gadk-rhoai
podman build --platform linux/amd64 -f deploy/Dockerfile.agent -t adk-agent:migration .
podman push quay.io/rbrhssa/adk-agent:migration

# Redeploy (no image rebuild needed for skill-only changes via ConfigMap)
oc rollout restart deployment/adk-web -n adk-web
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

Agent code uses [google-adk](https://github.com/google/adk-python) (Apache 2.0).
UI uses [adk-web](https://github.com/google/adk-web) (Apache 2.0).
