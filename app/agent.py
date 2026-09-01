"""OCP Virt Migration Agent -- ADK 2.0 Simplified Workflow.

Architecture modeled after Google's official ADK samples:
  - Ambient Expense Agent (graph + HITL + conditional routing)
  - Small Business Loan Agent (orchestrator + specialized sub-agents)

4 agents instead of 10, each doing meaningful LLM work:

  MigrationWorkflow (Workflow)
    START -> Coordinator (all tools + skills, handles ~93% ad-hoc queries)
          -> intent_router
               ├── "done"     -> END (Coordinator already answered)
               └── "pipeline" -> PreMigrationAgent (discover + assess + create plan)
                                   -> readiness_router
                                       ├── "ready" -> HITL approval -> approval_router
                                       │                ├── "approved" -> ExecutionAgent (execute + monitor)
                                       │                │                   -> outcome_router
                                       │                │                       ├── "terminal" -> PostMigrationAgent
                                       │                │                       └── "running"  -> ExecutionAgent (loop)
                                       │                └── "rejected" -> PostMigrationAgent (rejection report)
                                       └── "not_ready" -> PostMigrationAgent (assessment report)

ADK 2.0 features:
  - Workflow graph with conditional edges, HITL, and monitor loop
  - RunConfig with max_llm_calls safety limit
  - EventsCompactionConfig for context summarization
  - FunctionTool(require_confirmation=True) for destructive operations
  - MigrationLoggingPlugin for structured observability (via App.plugins)
  - MLflow tracing for tool + LLM call spans
  - ConfigMap-driven agent instructions and model tiers

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

from .callbacks import migration_safety_callback
from .shared.cluster_clients import DEFAULT_MTV_NAMESPACE, DEFAULT_VIRT_NAMESPACE
from .tools import (
    POST_MIGRATION_TEMPLATE_ID,
    PRE_MIGRATION_TEMPLATE_ID,
    check_cluster_readiness,
    create_migration_plan,
    execute_migration,
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
    validate_migrated_vm,
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
ADK_MODEL_FAST = os.environ.get("ADK_MODEL_FAST", "")
ADK_MODEL_REASONING = os.environ.get("ADK_MODEL_REASONING", "")
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
# Agent config loader (reads from ConfigMap YAML or falls back to defaults)
# ---------------------------------------------------------------------------
AGENT_CONFIG_PATH = os.environ.get("AGENT_CONFIG_PATH", "/mnt/config/agents.yaml")

_agent_config: dict = {}


def _load_agent_config() -> dict:
    """Load agent configuration from YAML file, with fallback to empty config."""
    global _agent_config
    if _agent_config:
        return _agent_config
    try:
        import yaml

        with open(AGENT_CONFIG_PATH) as f:
            _agent_config = yaml.safe_load(f) or {}
        log.info("Loaded agent config from %s (%d agents)", AGENT_CONFIG_PATH, len(_agent_config.get("agents", {})))
    except FileNotFoundError:
        log.info("No agent config at %s -- using built-in defaults", AGENT_CONFIG_PATH)
        _agent_config = {}
    except Exception as e:
        log.warning("Failed to load agent config: %s -- using defaults", e)
        _agent_config = {}
    return _agent_config


def _resolve_model(tier: str):
    """Resolve a model tier (fast/reasoning/default) to an actual model object."""
    config = _load_agent_config()
    defaults = config.get("defaults", {})

    if tier == "fast":
        model_str = ADK_MODEL_FAST or defaults.get("model_fast") or ADK_MODEL
    elif tier == "reasoning":
        model_str = ADK_MODEL_REASONING or defaults.get("model_reasoning") or ADK_MODEL
    else:
        model_str = defaults.get("model") or ADK_MODEL

    if model_str.startswith("gemini") and "/" not in model_str:
        return model_str
    return LiteLlm(model=model_str)


def _get_agent_instruction(agent_name: str, fallback: str) -> str:
    """Get instruction for an agent from config, with template variable substitution."""
    config = _load_agent_config()
    agents = config.get("agents", {})
    agent_cfg = agents.get(agent_name, {})
    instruction = agent_cfg.get("instruction", fallback)

    aap_hint = (
        f"AAP template ID: {PRE_MIGRATION_TEMPLATE_ID}. Launch via launch_job, poll get_job_status, retrieve get_job_output. "
        if PRE_MIGRATION_TEMPLATE_ID
        else "No AAP configured. Assess using inventory data and skills. "
    )
    aap_post_hint = (
        f"AAP template ID: {POST_MIGRATION_TEMPLATE_ID}. "
        if POST_MIGRATION_TEMPLATE_ID
        else "No AAP configured. Validate using APIs and skills. "
    )

    try:
        return instruction.format(
            mtv_namespace=DEFAULT_MTV_NAMESPACE,
            virt_namespace=DEFAULT_VIRT_NAMESPACE,
            aap_hint=aap_hint,
            aap_post_hint=aap_post_hint,
        )
    except KeyError:
        return instruction


def _get_agent_model(agent_name: str, fallback_tier: str = "default"):
    """Get the model for an agent from config."""
    config = _load_agent_config()
    agents = config.get("agents", {})
    tier = agents.get(agent_name, {}).get("model", fallback_tier)
    return _resolve_model(tier)


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
execute_migration = wrap_tool_with_trace(execute_migration)
validate_migrated_vm = wrap_tool_with_trace(validate_migrated_vm)


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
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Graph router functions (use ctx.state for per-session data, not globals)
# ---------------------------------------------------------------------------
_MAX_MONITOR_POLLS = int(os.environ.get("MAX_MONITOR_POLLS", "30"))


def intent_router(node_input=None):
    """Route coordinator output: pipeline (full migration) or done (ad-hoc answer)."""
    if node_input is None:
        return Event(route="done", output="")
    text = str(node_input.get("action", node_input) if isinstance(node_input, dict) else node_input).upper()
    if "PIPELINE" in text or "FULL MIGRATION" in text or "RUN MIGRATION" in text:
        return Event(route="pipeline", output=node_input)
    return Event(route="done", output=node_input)


def done_passthrough(node_input=None):
    """Terminal node -- Coordinator already answered the ad-hoc query."""
    return Event(output=node_input or "")


def readiness_router(node_input=None):
    """Deterministic: skip migration if assessment says NOT READY."""
    if node_input is None:
        return Event(route="not_ready", output="No assessment data")
    text = str(node_input.get("verdict", node_input) if isinstance(node_input, dict) else node_input)
    if "NOT READY" in text.upper():
        log.info("[Router] NOT READY -- skipping to report")
        return Event(route="not_ready", output=node_input)
    log.info("[Router] READY -- proceeding to approval")
    return Event(route="ready", output=node_input)


async def migration_approval(ctx: Context, node_input):
    """HITL: pause for human approval before triggering real migration."""
    plan_summary = ""
    if node_input:
        text = str(node_input)
        for marker in ("Plan '", "plan_name"):
            idx = text.find(marker)
            if idx >= 0:
                plan_summary = text[max(0, idx - 50) : idx + 100]
                break

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
    response = ctx.resume_inputs.get("migration_approval", "no")
    yield Event(output={"approval": str(response), "plan_context": plan_summary})


def approval_router(node_input):
    """Route based on human yes/no response."""
    text = str(node_input).strip().lower()
    if text in ("yes", "y", "approve", "approved", "proceed"):
        log.info("[Router] Migration APPROVED")
        return Event(route="approved", output=node_input)
    log.info("[Router] Migration REJECTED")
    return Event(route="rejected", output=node_input)


def outcome_router(ctx: Context, node_input=None):
    """Route execution result: terminal (completed/failed) or running (loop).

    Uses a single 'terminal' route for both completed and failed because the
    ADK Workflow graph does not allow duplicate from->to edges.
    PostMigrationAgent determines the action (validate vs rollback) from the
    execution_status content.
    """
    count = ctx.state.get("temp:monitor_poll_count", 0) + 1
    if node_input is None:
        node_input = ""
    status = str(node_input.get("status", node_input) if isinstance(node_input, dict) else node_input)
    if any(kw in status for kw in ("Failed", "Error", "Canceled", "Cancelled")):
        log.info("[Router] Migration FAILED -> terminal")
        return Event(route="terminal", output=status, state={"temp:monitor_poll_count": 0})
    if any(kw in status for kw in ("Completed", "Succeeded")):
        log.info("[Router] Migration COMPLETED -> terminal")
        return Event(route="terminal", output=status, state={"temp:monitor_poll_count": 0})
    if count >= _MAX_MONITOR_POLLS:
        log.warning("[Router] Monitor poll limit reached (%d), treating as failed", _MAX_MONITOR_POLLS)
        return Event(
            route="terminal",
            output=f"{status} (monitor timeout after {_MAX_MONITOR_POLLS} polls)",
            state={"temp:monitor_poll_count": 0},
        )
    log.info("[Router] Migration still running (poll %d/%d)", count, _MAX_MONITOR_POLLS)
    return Event(route="running", output=status, state={"temp:monitor_poll_count": count})


# ---------------------------------------------------------------------------
# Build the Hybrid Workflow graph
# ---------------------------------------------------------------------------
def _build_workflow():
    """Build the ADK 2.0 Simplified Workflow graph (4 agents)."""
    _load_agent_config()
    skill_tools = [SkillToolset(skills=skills)] if skills else []

    # Confirmation-gated tools for the Coordinator (ad-hoc safety)
    migration_plan_tool = FunctionTool(create_migration_plan, require_confirmation=True)
    coord_rollback_tool = FunctionTool(rollback_migration, require_confirmation=True)

    # -- Coordinator: handles ad-hoc queries + dispatches pipeline ---------
    coordinator = LlmAgent(
        name="Coordinator",
        model=_get_agent_model("Coordinator", "reasoning"),
        generate_content_config=genai_types.GenerateContentConfig(temperature=0.2),
        instruction=_get_agent_instruction(
            "Coordinator",
            "You are the Migration Coordinator. Use tools and skills to help with VMware-to-OCP Virt migrations.",
        ),
        tools=[
            list_vmware_vms,
            list_migrated_vms,
            get_migration_status,
            get_vm_details,
            migration_plan_tool,
            get_pod_logs,
            check_cluster_readiness,
            list_job_templates,
            launch_job,
            get_job_status,
            get_job_output,
            save_report_artifact,
            coord_rollback_tool,
            execute_migration,
            validate_migrated_vm,
            search_migration_history,
            record_migration,
            *skill_tools,
        ],
        before_tool_callback=migration_safety_callback,
        output_key="dispatch_result",
    )

    # -- PreMigrationAgent: discovery + assessment + plan creation ----------
    pre_migration_agent = LlmAgent(
        name="PreMigrationAgent",
        model=_get_agent_model("PreMigrationAgent", "reasoning"),
        instruction=_get_agent_instruction(
            "PreMigrationAgent",
            (
                "Load migration-workflow skill. Execute Phases 1-3: "
                "discover VMs via list_vmware_vms, assess readiness, "
                "then create the migration plan via create_migration_plan."
            ),
        ),
        tools=[
            list_vmware_vms,
            get_vm_details,
            check_cluster_readiness,
            create_migration_plan,
            launch_job,
            get_job_status,
            get_job_output,
            *skill_tools,
        ],
        output_key="pre_migration_result",
    )

    # -- ExecutionAgent: execute migration + monitor status -----------------
    execute_tool = FunctionTool(execute_migration, require_confirmation=True)
    execution_agent = LlmAgent(
        name="ExecutionAgent",
        model=_get_agent_model("ExecutionAgent", "fast"),
        instruction=_get_agent_instruction(
            "ExecutionAgent",
            (
                "Load migration-workflow skill Phases 4-5. "
                "Call execute_migration to start, then get_migration_status to check progress."
            ),
        ),
        tools=[execute_tool, get_migration_status, get_pod_logs, *skill_tools],
        before_tool_callback=migration_safety_callback,
        output_key="execution_status",
    )

    # -- PostMigrationAgent: validate OR rollback, then report -------------
    post_rollback_tool = FunctionTool(rollback_migration, require_confirmation=True)
    post_migration_agent = LlmAgent(
        name="PostMigrationAgent",
        model=_get_agent_model("PostMigrationAgent", "reasoning"),
        instruction=_get_agent_instruction(
            "PostMigrationAgent",
            (
                "Load post-migration-validator and completion-report-generator skills. "
                "If migration succeeded: validate and generate completion report. "
                "If migration failed: rollback and generate failure report. "
                "If migration was rejected or not ready: generate assessment-only report."
            ),
        ),
        tools=[
            validate_migrated_vm,
            list_migrated_vms,
            get_vm_details,
            post_rollback_tool,
            save_report_artifact,
            record_migration,
            launch_job,
            get_job_status,
            get_job_output,
            *skill_tools,
        ],
        output_key="final_report",
    )

    # -- Workflow graph (9 edges, 4 agents) --------------------------------
    workflow = Workflow(
        name=AGENT_NAME,
        description=AGENT_DESC,
        edges=[
            ("START", coordinator, intent_router),
            (intent_router, {"done": done_passthrough, "pipeline": pre_migration_agent}),
            (pre_migration_agent, readiness_router),
            (readiness_router, {"ready": migration_approval, "not_ready": post_migration_agent}),
            (migration_approval, approval_router),
            (approval_router, {"approved": execution_agent, "rejected": post_migration_agent}),
            (execution_agent, outcome_router),
            (outcome_router, {"terminal": post_migration_agent, "running": execution_agent}),
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
        model=_resolve_model("default"),
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
