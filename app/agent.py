"""OCP Virt Migration Agent -- ADK 2.0 Hybrid Workflow.

Uses an ADK 2.0 Workflow graph with a dispatcher-first pattern:

  MigrationWorkflow (Workflow -- root_agent via node= param)
    START -> Dispatcher (LlmAgent with ALL tools + skills)
          -> intent_router
               ├── "done"     -> DoneAgent (summarize ad-hoc result)
               ├── "pipeline" -> DiscoveryAgent -> AssessmentAgent
               │                   -> readiness_router
               │                       ├── "ready"     -> HITL approval -> approval_router
               │                       │                    ├── "approved" -> MigrationAgent -> StatusPoller
               │                       │                    │                   -> monitor_router
               │                       │                    │                       ├── "completed" -> ValidationAgent -> ReporterAgent
               │                       │                    │                       ├── "failed"    -> RollbackAgent -> ReporterAgent
               │                       │                    │                       └── "running"   -> StatusPoller (loop)
               │                       │                    └── "rejected" -> ReporterAgent
               │                       └── "not_ready" -> ReporterAgent
               └── "batch"    -> BatchPlannerAgent -> DiscoveryAgent (same pipeline)

ADK 2.0 features:
  - Workflow graph with conditional edges and HITL
  - RunConfig with max_llm_calls safety limit
  - EventsCompactionConfig for context summarization
  - FunctionTool(require_confirmation=True) for migration approval
  - MigrationLoggingPlugin for structured observability (via App.plugins)
  - MLflow tracing for tool + LLM call spans

Set AGENT_MODE=single to fall back to the legacy monolithic agent.
"""

import logging
import os
import pathlib

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App, ResumabilityConfig
from google.adk.apps.app import EventsCompactionConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.models.lite_llm import LiteLlm
from google.adk.skills import load_skill_from_dir
from google.adk.tools import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.workflow import Workflow
from google.genai import types as genai_types
from pydantic import BaseModel, Field

from .callbacks import migration_safety_callback
from .shared.cluster_clients import DEFAULT_MTV_NAMESPACE, DEFAULT_VIRT_NAMESPACE
from .tools import (
    POST_MIGRATION_TEMPLATE_ID,
    PRE_MIGRATION_TEMPLATE_ID,
    check_cluster_readiness,
    create_migration_plan,
    get_job_output,
    get_job_status,
    get_migration_status,
    get_pod_logs,
    get_vm_details,
    launch_job,
    list_job_templates,
    list_migrated_vms,
    list_vmware_vms,
    record_migration,
    rollback_migration,
    save_report_artifact,
    search_migration_history,
)
from .tracing import enable_tracing, wrap_tool_with_trace

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MLflow tracing (no-op when MLFLOW_TRACKING_URI is unset)
# ---------------------------------------------------------------------------
enable_tracing()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ADK_MODEL = os.environ.get("ADK_MODEL", "openai/gemini/models/gemini-2.5-flash")
SKILLS_DIR = pathlib.Path(os.environ.get("SKILLS_DIR", "/skills"))
AGENT_NAME = os.environ.get("AGENT_NAME", "migration_coordinator")
APP_NAME = "app"
AGENT_MODE = os.environ.get("AGENT_MODE", "pipeline")
MAX_LLM_CALLS = int(os.environ.get("MAX_LLM_CALLS", "200"))
COMPACTION_TOKEN_THRESHOLD = int(os.environ.get("COMPACTION_TOKEN_THRESHOLD", "16000"))
COMPACTION_EVENT_RETENTION = int(os.environ.get("COMPACTION_EVENT_RETENTION", "5"))
AGENT_DESC = os.environ.get(
    "AGENT_DESC",
    "VMware-to-OpenShift Virtualization migration coordinator with automated "
    "pipeline for discovery, assessment, migration, monitoring, validation, "
    "and report generation.",
)

# ---------------------------------------------------------------------------
# Wrap tool functions with MLflow TOOL spans (no-op when tracing is off)
# ---------------------------------------------------------------------------
list_vmware_vms = wrap_tool_with_trace(list_vmware_vms)
list_migrated_vms = wrap_tool_with_trace(list_migrated_vms)
get_migration_status = wrap_tool_with_trace(get_migration_status)
get_vm_details = wrap_tool_with_trace(get_vm_details)
create_migration_plan = wrap_tool_with_trace(create_migration_plan)
get_pod_logs = wrap_tool_with_trace(get_pod_logs)
list_job_templates = wrap_tool_with_trace(list_job_templates)
launch_job = wrap_tool_with_trace(launch_job)
get_job_status = wrap_tool_with_trace(get_job_status)
get_job_output = wrap_tool_with_trace(get_job_output)
save_report_artifact = wrap_tool_with_trace(save_report_artifact)
rollback_migration = wrap_tool_with_trace(rollback_migration)
check_cluster_readiness = wrap_tool_with_trace(check_cluster_readiness)


# ---------------------------------------------------------------------------
# Skill discovery
# ---------------------------------------------------------------------------
def _discover_skills(skills_dir: pathlib.Path) -> list:
    """Discover and load all skills from subdirectories containing SKILL.md."""
    skills = []
    if not skills_dir.exists():
        log.warning("Skills directory %s does not exist", skills_dir)
        return skills
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").exists():
            try:
                skill = load_skill_from_dir(entry)
                skills.append(skill)
                log.info("Loaded skill: %s", entry.name)
            except Exception as e:
                log.warning("Failed to load skill from %s: %s", entry, e)
    return skills


skills = _discover_skills(SKILLS_DIR)
log.info("Discovered %d skills from %s", len(skills), SKILLS_DIR)


# ---------------------------------------------------------------------------
# Pydantic output schemas for workflow agents (ADK best practice)
# ---------------------------------------------------------------------------
class DispatcherOutput(BaseModel):
    action: str = Field(description="PIPELINE:<vm> in <ns>, BATCH:<vms> in <ns>, or the complete answer")


class InventoryOutput(BaseModel):
    inventory: str = Field(description="JSON inventory of discovered VMs")


class AssessmentOutput(BaseModel):
    verdict: str = Field(description="READY or NOT READY with risk rating and details")


class MigrationOutput(BaseModel):
    result: str = Field(description="Migration plan name, migration name, and status")


class StatusOutput(BaseModel):
    status: str = Field(description="Migration phase and VM progress summary")


class ValidationOutput(BaseModel):
    result: str = Field(description="PASS or FAIL with comparison details")


class ReportOutput(BaseModel):
    report: str = Field(description="Formal migration report content")


# ---------------------------------------------------------------------------
# Graph router functions (use ctx.state for per-session data, not globals)
# ---------------------------------------------------------------------------
_MAX_MONITOR_POLLS = int(os.environ.get("MAX_MONITOR_POLLS", "30"))


def intent_router(node_input: dict):
    """Route dispatcher output: pipeline, batch, or done (ad-hoc answer)."""
    text = str(node_input.get("action", node_input) if isinstance(node_input, dict) else node_input).upper()
    if "PIPELINE" in text or "FULL MIGRATION" in text or "RUN MIGRATION" in text:
        return Event(route="pipeline", output=node_input)
    if "BATCH" in text or "MULTIPLE VMS" in text:
        return Event(route="batch", output=node_input)
    return Event(route="done", output=node_input)


def readiness_router(node_input: dict):
    """Deterministic: skip migration if assessment says NOT READY."""
    text = str(node_input.get("verdict", node_input) if isinstance(node_input, dict) else node_input)
    if "NOT READY" in text.upper():
        log.info("[Router] NOT READY -- skipping to report")
        return Event(route="not_ready", output=node_input)
    log.info("[Router] READY -- proceeding to approval")
    return Event(route="ready", output=node_input)


async def migration_approval(ctx: Context, node_input):
    """HITL: pause for human approval before triggering real migration."""
    if not ctx.resume_inputs:
        yield RequestInput(
            interrupt_id="migration_approval",
            message=(
                "The VM has been assessed as READY for migration. "
                "Do you approve proceeding with the VMware-to-OCP Virtualization "
                "migration? (Type 'yes' to approve or 'no' to cancel)"
            ),
        )
        return
    yield Event(output=ctx.resume_inputs.get("migration_approval", "no"))


def approval_router(node_input):
    """Route based on human yes/no response."""
    text = str(node_input).strip().lower()
    if text in ("yes", "y", "approve", "approved", "proceed"):
        log.info("[Router] Migration APPROVED")
        return Event(route="approved", output=node_input)
    log.info("[Router] Migration REJECTED")
    return Event(route="rejected", output=node_input)


def monitor_router(ctx: Context, node_input: dict):
    """Route monitor loop: completed/failed/running. Per-session poll counter via ctx.state."""
    count = ctx.state.get("temp:monitor_poll_count", 0) + 1
    status = str(node_input.get("status", node_input) if isinstance(node_input, dict) else node_input)

    if any(kw in status for kw in ("Failed", "Error", "Canceled", "Cancelled")):
        log.info("[Router] Migration FAILED")
        return Event(route="failed", output=status, state={"temp:monitor_poll_count": 0})
    if any(kw in status for kw in ("Completed", "Succeeded")):
        log.info("[Router] Migration COMPLETED")
        return Event(route="completed", output=status, state={"temp:monitor_poll_count": 0})
    if count >= _MAX_MONITOR_POLLS:
        log.warning("[Router] Monitor poll limit reached (%d), treating as failed", _MAX_MONITOR_POLLS)
        return Event(
            route="failed",
            output=f"{status} (monitor timeout after {_MAX_MONITOR_POLLS} polls)",
            state={"temp:monitor_poll_count": 0},
        )
    log.info("[Router] Migration still running (poll %d/%d)", count, _MAX_MONITOR_POLLS)
    return Event(route="running", output=status, state={"temp:monitor_poll_count": count})


# ---------------------------------------------------------------------------
# Build the Hybrid Workflow graph
# ---------------------------------------------------------------------------
def _build_workflow():
    """Build the ADK 2.0 Hybrid Workflow graph."""
    if ADK_MODEL.startswith("gemini") and "/" not in ADK_MODEL:
        model = ADK_MODEL
    else:
        model = LiteLlm(model=ADK_MODEL)
    skill_tools = [SkillToolset(skills=skills)] if skills else []
    migration_tool = FunctionTool(create_migration_plan, require_confirmation=True)
    rollback_tool = FunctionTool(rollback_migration, require_confirmation=True)

    # -- Dispatcher: handles ad-hoc queries with all tools -----------------
    dispatcher = LlmAgent(
        name="Dispatcher",
        model=model,
        generate_content_config=genai_types.GenerateContentConfig(temperature=0.2),
        instruction=(
            "You are the Migration Coordinator for VMware-to-OpenShift Virtualization.\n\n"
            "## How to respond\n"
            "For most queries, use your tools and skills directly and give "
            "the user a complete answer. ALWAYS load the relevant skill BEFORE "
            "answering knowledge questions -- do NOT answer from memory alone.\n\n"
            "## When to trigger the pipeline\n"
            "ONLY when the user explicitly asks to run a full end-to-end migration "
            "(e.g., 'migrate VM X', 'run full migration for Y'), output the exact "
            "text 'PIPELINE: <vm_name> in <namespace>' as your response.\n\n"
            "For batch migrations of multiple VMs, output 'BATCH: <vm_list> in <namespace>'.\n\n"
            "## Available tools\n"
            "- list_vmware_vms / list_migrated_vms / get_vm_details / get_migration_status\n"
            "- create_migration_plan / get_pod_logs / check_cluster_readiness\n"
            "- list_job_templates / launch_job / get_job_status / get_job_output\n"
            "- save_report_artifact / rollback_migration\n"
            "- search_migration_history / record_migration\n\n"
            "## Skills -- ALWAYS load the matching skill for these topics\n"
            "| Question about | Load this skill | Then read this reference |\n"
            "| VMware vs OCP Virt features, vSphere EOL, licensing, OCP Virt 4.21 features | vmware-feature-mapper | references/feature-map.md, references/vmware-eol-context.md |\n"
            "| Migration types (cold/warm/live), MTV 2.11, workflow steps | migration-workflow | SKILL.md |\n"
            "| MTV errors, failures, stuck migrations, troubleshooting | mtv-log-analyzer | references/common-mtv-failures.md, references/production-failure-patterns.md |\n"
            "| Storage options, CSI drivers, DR, storage copy offload | storage-advisor | references/csi-comparison.md, references/storage-copy-offload.md |\n"
            "| Network design, NIC bonding, NADs, SR-IOV, UDN | network-architect | references/design-patterns.md |\n"
            "| Cluster readiness, version compatibility, operator checks | cluster-preflight | references/compatibility-matrix.md |\n"
            "| Pre-migration assessment, playbook output analysis | pre-migration-analyzer + ansible-output-parser | |\n"
            "| Post-migration validation | post-migration-validator | |\n"
            "| Day-2 operations, live migration, snapshots, GPU, hugepages | day2-operations | |\n"
            "| Batch planning, wave scheduling, capacity sizing | batch-planner + capacity-analyzer + risk-assessor | |\n"
            "| Report generation | assessment-report-generator or completion-report-generator | |\n\n"
            f"Defaults: MTV namespace={DEFAULT_MTV_NAMESPACE}, "
            f"Virt namespace={DEFAULT_VIRT_NAMESPACE}\n\n"
            "Always explain what you're doing. Produce structured, actionable output."
        ),
        tools=[
            list_vmware_vms,
            list_migrated_vms,
            get_migration_status,
            get_vm_details,
            migration_tool,
            get_pod_logs,
            check_cluster_readiness,
            list_job_templates,
            launch_job,
            get_job_status,
            get_job_output,
            save_report_artifact,
            rollback_tool,
            search_migration_history,
            record_migration,
            *skill_tools,
        ],
        before_tool_callback=migration_safety_callback,
        output_schema=DispatcherOutput,
        output_key="dispatch_result",
    )

    # -- Done: summarizes ad-hoc results -----------------------------------
    done_agent = LlmAgent(
        name="DoneAgent",
        model=model,
        instruction="Summarize the dispatcher's result for the user in a clear, helpful format.",
        output_key="final_answer",
    )

    # -- Batch planner: plans multi-VM migrations --------------------------
    batch_planner = LlmAgent(
        name="BatchPlannerAgent",
        model=model,
        instruction=(
            "You plan batch migrations for multiple VMs.\n\n"
            "Load the `batch-planner` and `risk-assessor` skills. Given the list "
            "of VMs, group them into batches by risk, OS, and dependencies.\n\n"
            "Consider cluster capacity using the `capacity-analyzer` skill.\n\n"
            "## Smart Scheduling\n"
            "Suggest optimal migration windows based on:\n"
            "- Batch size (5-10 VMs per batch)\n"
            "- Risk diversity (don't put all high-risk VMs in one batch)\n"
            "- OS diversity (spread OS types across batches)\n"
            "- Timeline (24h between batches for validation)\n"
            "- Off-peak hours for production VMs\n\n"
            "Output a structured batch plan with timeline."
        ),
        tools=[list_vmware_vms, *skill_tools],
        output_key="batch_plan",
    )

    # -- Pipeline agents ---------------------------------------------------
    discovery_agent = LlmAgent(
        name="DiscoveryAgent",
        model=model,
        instruction=(
            "Discover VMware VMs for migration.\n"
            f"Call `list_vmware_vms` (default namespace: {DEFAULT_MTV_NAMESPACE}). "
            "Output the full VM inventory as structured JSON."
        ),
        tools=[list_vmware_vms],
        output_schema=InventoryOutput,
        output_key="vm_inventory",
    )

    _pre_hint = (
        f"AAP template ID: {PRE_MIGRATION_TEMPLATE_ID}. "
        "Launch via launch_job, poll get_job_status, retrieve get_job_output. "
        if PRE_MIGRATION_TEMPLATE_ID
        else "No AAP configured. Assess using inventory data and skills. "
    )

    assessment_agent = LlmAgent(
        name="AssessmentAgent",
        model=model,
        instruction=(
            "Analyze migration readiness.\n"
            "VM inventory is in session state 'vm_inventory'.\n"
            f"{_pre_hint}"
            "Load ansible-output-parser, pre-migration-analyzer, risk-assessor skills.\n"
            "Output verdict: READY or NOT READY with risk rating and details."
        ),
        tools=[launch_job, get_job_status, get_job_output, *skill_tools],
        output_schema=AssessmentOutput,
        output_key="readiness_verdict",
    )

    migration_agent = LlmAgent(
        name="MigrationAgent",
        model=model,
        instruction=(
            "Trigger the VMware-to-OCP migration.\n"
            "The user has approved. Call create_migration_plan with the correct "
            "namespace and VM name from session state."
        ),
        tools=[migration_tool],
        before_tool_callback=migration_safety_callback,
        output_schema=MigrationOutput,
        output_key="migration_id",
    )

    monitor_poller = LlmAgent(
        name="StatusPoller",
        model=model,
        instruction=(
            "Monitor the in-progress migration.\n"
            "Call get_migration_status. Report phase, VMs completed/running/failed.\n"
            "If errors, call get_pod_logs and load mtv-log-analyzer skill.\n"
            "Output a status summary."
        ),
        tools=[get_migration_status, get_pod_logs, *skill_tools],
        output_schema=StatusOutput,
        output_key="migration_status",
    )

    _post_hint = (
        f"AAP template ID: {POST_MIGRATION_TEMPLATE_ID}. "
        if POST_MIGRATION_TEMPLATE_ID
        else "No AAP configured. Validate using APIs and skills. "
    )

    validation_agent = LlmAgent(
        name="ValidationAgent",
        model=model,
        instruction=(
            "Validate post-migration results.\n"
            f"{_post_hint}"
            "Compare migrated VM against source inventory in 'vm_inventory'.\n"
            "Load post-migration-validator skill. Output PASS or FAIL verdict."
        ),
        tools=[list_migrated_vms, get_vm_details, launch_job, get_job_status, get_job_output, *skill_tools],
        output_schema=ValidationOutput,
        output_key="validation_result",
    )

    rollback_agent = LlmAgent(
        name="RollbackAgent",
        model=model,
        instruction=(
            "The migration has failed. Clean up the created resources.\n"
            "Read 'migration_id' from session state to get the plan name and namespace.\n"
            "Call rollback_migration to delete the Migration, Plan, StorageMap, "
            "and NetworkMap CRs. Then call record_migration to save the failure record.\n"
            "Output what was cleaned up and the failure details."
        ),
        tools=[rollback_tool, record_migration],
        output_key="rollback_result",
    )

    reporter_agent = LlmAgent(
        name="ReporterAgent",
        model=model,
        instruction=(
            "Generate a formal migration report from session state.\n"
            "Load the completion-report-generator skill.\n"
            "Include: summary, before/after comparison, assessment, timeline, "
            "validation results, outstanding items, sign-off.\n"
            "Call save_report_artifact to persist the report.\n"
            "Call record_migration to save the outcome to history."
        ),
        tools=[save_report_artifact, record_migration, *skill_tools],
        output_schema=ReportOutput,
        output_key="final_report",
    )

    # -- Workflow graph ----------------------------------------------------
    workflow = Workflow(
        name=AGENT_NAME,
        description=AGENT_DESC,
        edges=[
            # Dispatcher handles all queries, router decides next step
            ("START", dispatcher, intent_router),
            # Ad-hoc queries go to done
            (intent_router, {"done": done_agent, "pipeline": discovery_agent, "batch": batch_planner}),
            # Batch planning feeds into the same pipeline
            (batch_planner, discovery_agent),
            # Pipeline: discovery -> assessment -> readiness check
            (discovery_agent, assessment_agent, readiness_router),
            (readiness_router, {"ready": migration_approval, "not_ready": reporter_agent}),
            # HITL approval
            (migration_approval, approval_router),
            (approval_router, {"approved": migration_agent, "rejected": reporter_agent}),
            # Migration -> monitoring loop
            (migration_agent, monitor_poller, monitor_router),
            (monitor_router, {"completed": validation_agent, "failed": rollback_agent, "running": monitor_poller}),
            # Validation -> report
            (validation_agent, reporter_agent),
            # Rollback -> report
            (rollback_agent, reporter_agent),
        ],
    )

    return workflow


# ---------------------------------------------------------------------------
# Single mode: legacy monolithic agent
# ---------------------------------------------------------------------------
_SINGLE_INSTRUCTION = (
    "You are an expert in VMware-to-OpenShift Virtualization migrations.\n\n"
    "## Tools\n"
    "- list_vmware_vms / list_migrated_vms / get_vm_details / get_migration_status\n"
    "- create_migration_plan / get_pod_logs / rollback_migration / check_cluster_readiness\n"
    "- list_job_templates / launch_job / get_job_status / get_job_output\n"
    "- save_report_artifact / search_migration_history / record_migration\n\n"
    "## Skills (load on demand)\n"
    "- ansible-output-parser, pre-migration-analyzer, post-migration-validator\n"
    "- assessment-report-generator, completion-report-generator, mtv-log-analyzer\n"
    "- capacity-analyzer, risk-assessor, batch-planner\n\n"
    "Always explain what you're doing. Produce structured, actionable reports.\n"
    f"Default MTV namespace: {DEFAULT_MTV_NAMESPACE}. "
    f"Default Virt namespace: {DEFAULT_VIRT_NAMESPACE}."
)


def _build_single_agent() -> LlmAgent:
    """Build the legacy single-agent fallback."""
    if ADK_MODEL.startswith("gemini") and "/" not in ADK_MODEL:
        model = ADK_MODEL
    else:
        model = LiteLlm(model=ADK_MODEL)
    migration_tool = FunctionTool(create_migration_plan, require_confirmation=True)
    rollback_tool = FunctionTool(rollback_migration, require_confirmation=True)
    skill_tools = [SkillToolset(skills=skills)] if skills else []

    tools = [
        *skill_tools,
        list_vmware_vms,
        list_migrated_vms,
        get_migration_status,
        get_vm_details,
        migration_tool,
        get_pod_logs,
        check_cluster_readiness,
        list_job_templates,
        launch_job,
        get_job_status,
        get_job_output,
        save_report_artifact,
        rollback_tool,
        search_migration_history,
        record_migration,
    ]

    return LlmAgent(
        model=model,
        name=os.environ.get("AGENT_NAME", "migration_agent"),
        description=AGENT_DESC,
        instruction=_SINGLE_INSTRUCTION,
        tools=tools,
        before_tool_callback=migration_safety_callback,
    )


# ---------------------------------------------------------------------------
# Build root_agent based on AGENT_MODE
# ---------------------------------------------------------------------------
log.info("Agent mode: %s", AGENT_MODE)

if AGENT_MODE == "single":
    log.info("Building legacy single-agent")
    root_agent = _build_single_agent()
else:
    log.info("Building ADK 2.0 Hybrid Workflow")
    root_agent = _build_workflow()

log.info("Root agent ready: %s", root_agent.name)

# ---------------------------------------------------------------------------
# ADK App with context compaction and plugins
# ---------------------------------------------------------------------------
from .plugins import MigrationLoggingPlugin

app = App(
    name=APP_NAME,
    root_agent=root_agent,
    plugins=[MigrationLoggingPlugin()],
    resumability_config=ResumabilityConfig(is_resumable=True),
    events_compaction_config=EventsCompactionConfig(
        token_threshold=COMPACTION_TOKEN_THRESHOLD,
        event_retention_size=COMPACTION_EVENT_RETENTION,
    ),
)

# ---------------------------------------------------------------------------
# Default RunConfig with safety limits
# ---------------------------------------------------------------------------
default_run_config = RunConfig(
    max_llm_calls=MAX_LLM_CALLS,
    streaming_mode=StreamingMode.SSE,
)
