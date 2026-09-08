# Demo Speaker Notes

Tell-Show-Tell format for each architecture diagram. Use these as talking points when presenting the OCP Virt Migration Agent.

---

## Diagram 1: OpenShift Deployment Architecture

### TELL (set the context)

"This agent runs as a single pod on OpenShift, deployed via GitOps. It's built on Google's Agent Development Kit -- ADK 2.0 -- and packaged as a standard container image with everything baked in: the agent code, 18 specialized skills, and the ADK web interface. There's no complex infrastructure -- just a pod, a ConfigMap for instructions, and a SealedSecret for tokens."

### SHOW (walk through the diagram)

- **Browser** connects through an OpenShift Route with TLS termination
- **Two endpoints** are exposed: port 8080 for the agent API (chat, health checks, HITL approvals) and port 8081 for the Google ADK Web UI which gives you full visibility into agent reasoning, tool calls, and traces
- **The pod** has the Migration Agent container with 18 skills loaded at startup in pipeline mode
- **ConfigMap** controls the agent's personality and behavior -- each of the 4 agents has its own instruction set, model tier, and temperature
- **SealedSecret** holds the MTV cluster token and the Gemini API key -- never stored in plaintext in the repo
- **Skills are baked into the image** at build time -- 18 markdown-based knowledge modules covering everything from migration workflows to network architecture to troubleshooting

### TELL (key takeaway)

"The deployment is intentionally simple. One pod, GitOps-managed, with all intelligence in the agent instructions and skills -- not in complex infrastructure. Push to main, CI builds the image, ArgoCD syncs the config."

---

## Diagram 2: Multi-Agent Pipeline Architecture

### TELL (set the context)

"The agent uses a 4-agent workflow graph -- not a simple chatbot. When you ask it to migrate a VM, it orchestrates a multi-step pipeline with built-in safety gates. Most interactions -- about 93% -- are handled directly by the Coordinator as ad-hoc queries. Only explicit migration requests trigger the full pipeline."

### SHOW (walk through the diagram)

- **Coordinator** is the entry point. It handles questions like 'list my VMs', 'check cluster readiness', 'what's been migrated'. When it sees an explicit migration request like 'migrate database-user1', it outputs `PIPELINE:` which triggers the workflow
- **intent_router** -- this is a code-controlled decision, not an LLM guess. If the Coordinator said PIPELINE, we go to PreMigration. Otherwise, we're done -- the Coordinator already answered
- **PreMigrationAgent** discovers the VM from VMware inventory, assesses readiness against 30+ criteria, and creates the migration plan -- NetworkMap, StorageMap, and Plan CRs on the MTV cluster
- **readiness_router** checks the verdict. If NOT READY, we skip straight to PostMigration for an assessment report. No migration happens
- **HITL gate** -- this is critical. The workflow STOPS here and asks the human: 'Do you approve this migration?' Nothing proceeds without explicit approval. This is a native ADK feature, not a hack
- **ExecutionAgent** creates the Migration CR and monitors progress. It polls every 20-30 seconds with a budget of 90 polls -- enough for migrations up to 30+ minutes
- **outcome_router** loops back to ExecutionAgent while the migration is running. When it sees Succeeded or Failed, it routes to terminal
- **PostMigrationAgent** uses the reasoning model -- it validates the migrated VM, generates a completion report, or handles rollback if something failed

### TELL (key takeaway)

"Four agents, each with a focused job. The Coordinator is the friendly face. PreMigration is the careful planner. Execution is the patient monitor. PostMigration is the thorough validator. And the HITL gate means no migration ever runs without a human saying yes."

---

## Diagram 3: Multi-Cluster Connectivity

### TELL (set the context)

"The agent doesn't just talk to one cluster -- it connects to up to 5 external systems, each with independent authentication. This is a multi-cluster architecture where the agent runs on one cluster but operates across multiple environments."

### SHOW (walk through the diagram)

- **Center: Agent Pod** -- contains four key modules: `ocp_tools.py` for migration operations, `aap_tools.py` for Ansible Automation Platform integration, `cluster_clients.py` which manages all the Kubernetes connections, and `LiteLlm` for LLM communication
- **MTV Cluster** (top-left) -- this is where Forklift lives. The agent creates Plans, Migrations, NetworkMaps, and StorageMaps here via the Forklift API. It also queries the Inventory Route to discover VMware VMs. Two separate connections: K8s API for CRs, HTTP for inventory
- **OCP Virt Cluster** (top-right) -- where migrated VMs land. The agent queries KubeVirt to validate VMs post-migration and reads pod logs for troubleshooting. In this lab, MTV and Virt happen to be the same physical cluster, differentiated by namespace
- **AAP Controller** (bottom-left) -- optional integration with Ansible Automation Platform for running pre-migration and post-migration playbooks. The agent can launch jobs, poll status, and parse the output
- **LLM Endpoint** (bottom-right) -- OpenAI-compatible API. We're using Gemini 2.5 Flash for the fast agents and Gemini 2.5 Pro for reasoning, served through a MaaS gateway
- **MLflow** (bottom) -- all tool calls and LLM interactions are traced to MLflow for observability
- **Lock icons** on every connection -- each has its own token, CA bundle configuration, and retry logic. Tokens support file-path indirection for rotation

### TELL (key takeaway)

"Every connection has retries with exponential backoff, token rotation support, and independent TLS configuration. The agent is designed to be resilient -- a transient network blip won't kill a 15-minute migration."

---

## Diagram 4: Tool and Skill Access Matrix

### TELL (set the context)

"Not every agent needs every tool. We follow the principle of least privilege -- each agent only gets the tools it needs for its specific job. This prevents the LLM from calling the wrong tool at the wrong time."

### SHOW (walk through the diagram)

- **Coordinator** gets everything -- all 15 tools plus the SkillToolset. It needs this because in ad-hoc mode, users can ask anything
- **PreMigrationAgent** gets discovery and planning tools: `list_vmware_vms` to find VMs, `check_cluster_readiness` to verify the environment, `create_migration_plan` to build the plan. Notice it does NOT have `execute_migration` -- it cannot accidentally start a migration
- **ExecutionAgent** is focused: `execute_migration` to start, `get_migration_status` to monitor, `get_pod_logs` for troubleshooting. That's it. It cannot create plans or validate VMs
- **PostMigrationAgent** gets validation and reporting tools: `validate_migrated_vm`, `rollback_migration`, `save_report_artifact`. It also gets the AAP tools for running post-migration playbooks
- **SkillToolset** -- all 4 agents can load skills on demand. 18 skills covering migration workflows, troubleshooting, network design, storage options, and more. Skills are loaded only when needed, keeping the context window lean

### TELL (key takeaway)

"This isn't just organization -- it's safety. The ExecutionAgent can't create plans. The PreMigrationAgent can't execute migrations. Each agent stays in its lane, and the HITL gate is the explicit handoff between planning and execution."

---

## Diagram 5: Data Flow Through the Pipeline

### TELL (set the context)

"Let me walk you through exactly what happens when you say 'migrate database-user1' -- from the first word to the final report. Every piece of data flows through session state keys, and each agent builds on what the previous one discovered."

### SHOW (walk through the diagram)

- **User says 'migrate database-user1'** -- the Coordinator recognizes this as a migration request and outputs `PIPELINE: database-user1` into `dispatch_result`
- **intent_router** sees the PIPELINE keyword and routes to PreMigrationAgent. If the user had asked 'what VMs do I have?', it would route to 'done' and the Coordinator's answer goes directly back
- **PreMigrationAgent** calls `list_vmware_vms`, finds the VM, assesses readiness, and calls `create_migration_plan` which creates the NetworkMap, StorageMap, and Plan CRs. All of this goes into `pre_migration_result`
- **readiness_router** checks the verdict. If the VM has blockers, it routes to PostMigration for an assessment-only report. No migration, no risk
- **HITL Approval** -- the workflow pauses. The user sees the plan details and clicks Approve or Decline. This is real human-in-the-loop, not a rubber stamp
- **ExecutionAgent** creates the Migration CR and starts polling. Every 20-30 seconds it checks `get_migration_status`. The `outcome_router` loops it back while the migration is running -- this loop can run for up to 30 minutes
- **PostMigrationAgent** runs `validate_migrated_vm` -- 8 automated checks: VM exists, status, guest agent, compute, storage, networking, labels. It writes the `final_report`
- **Session State bar** at the bottom shows how data accumulates: `dispatch_result` -> `pre_migration_result` -> `execution_status` -> `final_report`. Each agent reads from the previous keys

### TELL (key takeaway)

"The key insight is the branching. Not every path leads to a migration. If the VM isn't ready, you get an assessment report. If the human says no, you get a rejection report. If the migration fails, you get a rollback and failure report. Every outcome is documented."

---

## Live Demo Flow

After the slides, transition to the live demo with:

"Now let me show you this in action. I'm going to open the agent's chat interface and walk through a real migration that already completed -- then we'll look at what it takes to trigger a new one."

### Demo Script

**1. Show what's available** (30 seconds)
> Prompt: "List the VMware VMs available for migration"

The agent calls `list_vmware_vms` and shows 4 VMs from vSphere with specs.

**2. Show the completed migration** (30 seconds)
> Prompt: "What VMs have been migrated to OpenShift?"

Shows `database-user1` alongside `winweb01` and `winweb02` in `vmimported-user1`.

**3. Validate the migration** (30 seconds)
> Prompt: "Validate the database-user1 migration and show me its details"

Runs 8 automated post-migration checks. Shows PASS/FAIL for each. Shows `creationTimestamp` proving when the migration happened.

**4. Check readiness** (15 seconds)
> Prompt: "Is my cluster ready for more migrations?"

Shows worker nodes, storage classes, MTV providers -- all PASS.

**5. (Optional) Trigger a live migration** (5-10 minutes)
> Prompt: "Migrate haproxy-user1"

Full pipeline: discovery -> assessment -> plan creation -> HITL approval (click Approve) -> execution -> monitoring -> validation -> report. The 4GB disk migrates in about 3-5 minutes.

### Key Talking Points During Demo

- "Notice the agent loaded the pre-migration-analyzer skill before assessing -- it's pulling in domain knowledge on demand"
- "The HITL gate here is native to ADK 2.0 -- the workflow actually pauses until I click Approve"
- "Watch the monitoring -- it polls every 20-30 seconds, giving us a status update each time"
- "The stale CR cleanup means I can re-run this migration without manually cleaning up -- the agent handles it"
- "All of this is running on OpenShift with Gemini 2.5 as the LLM, connecting to a real VMware vCenter and MTV cluster"
