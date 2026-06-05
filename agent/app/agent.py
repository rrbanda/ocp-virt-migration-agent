"""OCP Virt Migration Agent -- multi-agent ADK workflow architecture.

Refactored from a single monolithic LlmAgent to a proper ADK multi-agent
pipeline using SequentialAgent, LoopAgent, and artifact-based report
persistence.

Architecture:
  Coordinator (root_agent, LlmAgent)
    ├── MigrationPipeline (SequentialAgent)
    │     ├── DiscoveryAgent      -> output_key: vm_inventory
    │     ├── AssessmentAgent     -> output_key: readiness_verdict
    │     ├── MigrationAgent      -> output_key: migration_id
    │     ├── MigrationMonitor    (LoopAgent)
    │     │     ├── StatusPoller  -> output_key: migration_status
    │     │     └── StatusChecker (BaseAgent, escalates on terminal)
    │     ├── ValidationAgent     -> output_key: validation_result
    │     └── ReporterAgent       -> output_key: final_report
    └── (direct tools for ad-hoc queries)

Set AGENT_MODE=single to fall back to the original monolithic agent.

Configuration via environment variables:
  ADK_MODEL               - LLM model string (default: openai/gemini/models/gemini-2.5-flash)
  SKILLS_DIR              - Path to skills directory (default: /skills)
  AGENT_NAME              - Root agent name (default: migration_coordinator)
  AGENT_DESC              - Root agent description
  AGENT_INSTRUCTION_FILE  - Path to a markdown file with custom coordinator instruction
  AAP_URL                 - AAP Controller URL for job management
  AAP_TOKEN               - AAP API Bearer token (from Secret -- never hardcode)
  AGENT_MODE              - 'pipeline' (default) or 'single' (legacy fallback)
  MONITOR_MAX_ITERATIONS  - Max polling loops for migration monitor (default: 20)
  MONITOR_POLL_INTERVAL   - Seconds between monitor polls (default: 15)
"""

import logging
import os
import pathlib

from google.adk.agents import LlmAgent
from google.adk.agents.loop_agent import LoopAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

from .aap_tools import (
    PRE_MIGRATION_TEMPLATE_ID,
    POST_MIGRATION_TEMPLATE_ID,
    get_job_output,
    get_job_status,
    launch_job,
    list_job_templates,
)
from .migration_monitor import MigrationStatusChecker
from .cluster_clients import DEFAULT_MTV_NAMESPACE, DEFAULT_VIRT_NAMESPACE
from .ocp_tools import (
    create_migration_plan,
    get_migration_status,
    get_pod_logs,
    get_vm_details,
    list_migrated_vms,
    list_vmware_vms,
)
from .report_tools import save_report_artifact

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ADK_MODEL = os.environ.get("ADK_MODEL", "openai/gemini/models/gemini-2.5-flash")
SKILLS_DIR = pathlib.Path(os.environ.get("SKILLS_DIR", "/skills"))
AGENT_NAME = os.environ.get("AGENT_NAME", "migration_coordinator")
AGENT_MODE = os.environ.get("AGENT_MODE", "pipeline")
MONITOR_MAX_ITERATIONS = int(os.environ.get("MONITOR_MAX_ITERATIONS", "20"))
AGENT_DESC = os.environ.get(
    "AGENT_DESC",
    "VMware-to-OpenShift Virtualization migration coordinator with automated "
    "pipeline for discovery, assessment, migration, monitoring, validation, "
    "and report generation.",
)


# ---------------------------------------------------------------------------
# Skill discovery (shared across both modes)
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

aap_url = os.environ.get("AAP_URL", "")
if aap_url:
    log.info("AAP integration enabled: %s", aap_url)
else:
    log.info("AAP integration disabled (AAP_URL not set)")


# ---------------------------------------------------------------------------
# Instruction loader (for coordinator or single-agent fallback)
# ---------------------------------------------------------------------------
def _load_instruction() -> str:
    instruction_file = os.environ.get("AGENT_INSTRUCTION_FILE")
    if instruction_file and pathlib.Path(instruction_file).exists():
        return pathlib.Path(instruction_file).read_text()
    return os.environ.get("AGENT_INSTRUCTION", _COORDINATOR_INSTRUCTION)


# ---------------------------------------------------------------------------
# Pipeline mode: multi-agent architecture
# ---------------------------------------------------------------------------
def _build_pipeline_agent() -> LlmAgent:
    """Build the full multi-agent coordinator with a SequentialAgent pipeline."""

    model = LiteLlm(model=ADK_MODEL)

    skill_tools = [SkillToolset(skills=skills)] if skills else []

    # -- Phase 1: Discovery ------------------------------------------------
    discovery_agent = LlmAgent(
        name="DiscoveryAgent",
        model=model,
        instruction=(
            "You discover VMware VMs available for migration.\n\n"
            "Call `list_vmware_vms` with the namespace from the user's request "
            f"(default: {DEFAULT_MTV_NAMESPACE}). Output the full VM inventory as structured "
            "JSON including name, power state, OS, CPU, memory, disk, and "
            "firmware for every VM found."
        ),
        tools=[list_vmware_vms],
        output_key="vm_inventory",
    )

    # -- Phase 2: Assessment -----------------------------------------------
    _pre_template_hint = (
        f"The pre-migration AAP job template ID is {PRE_MIGRATION_TEMPLATE_ID}. "
        "Launch it via `launch_job(template_id)` with the VM hostname as extra_vars. "
        "Poll `get_job_status(job_id)` until complete, then retrieve the full "
        "output with `get_job_output(job_id)`. "
        if PRE_MIGRATION_TEMPLATE_ID else
        "No PRE_MIGRATION_TEMPLATE_ID is configured. Perform assessment "
        "using MTV inventory data and skills only. "
    )

    assessment_agent = LlmAgent(
        name="AssessmentAgent",
        model=model,
        instruction=(
            "You are a migration readiness analyst.\n\n"
            "The VM inventory is in the session state under key 'vm_inventory'.\n\n"
            "## AAP Pre-Migration Assessment\n"
            f"{_pre_template_hint}"
            "Once you have the playbook output, load the `ansible-output-parser` "
            "skill and parse the output. Use `load_skill_resource` to read "
            "`references/premigration-task-map.md` for the task-to-category mapping.\n\n"
            "## Analysis\n"
            "From the parsed results, evaluate each category:\n"
            "- Hypervisor, OS, Kernel/Boot, RPM Database, Disk/Filesystem\n"
            "- Package readiness, NFS/Remote FS, Backup, CMDB, Timezone\n\n"
            "Load the `risk-assessor` skill for risk classification.\n\n"
            "## Report\n"
            "Load the `assessment-report-generator` skill and produce a formal "
            "readiness report. Output a structured verdict:\n"
            "- **READY** or **NOT READY**\n"
            "- Risk rating (LOW / MEDIUM / HIGH / CRITICAL)\n"
            "- Blockers, Warnings, Recommendations"
        ),
        tools=[launch_job, get_job_status, get_job_output, *skill_tools],
        output_key="readiness_verdict",
    )

    # -- Phase 3: Migration trigger ----------------------------------------
    migration_agent = LlmAgent(
        name="MigrationAgent",
        model=model,
        instruction=(
            "You trigger VMware-to-OCP Virtualization migrations.\n\n"
            "The readiness verdict is in session state key 'readiness_verdict'. "
            "The VM inventory is in session state key 'vm_inventory'.\n\n"
            "If the verdict is READY: call `create_migration_plan` with the "
            "correct namespace and VM name. Output the plan name, migration "
            "name, and target namespace.\n\n"
            "If the verdict is NOT READY: output the blockers and explain why "
            "migration cannot proceed. Do NOT call create_migration_plan."
        ),
        tools=[create_migration_plan],
        output_key="migration_id",
    )

    # -- Phase 4: Migration monitor (LoopAgent) ----------------------------
    monitor_poller = LlmAgent(
        name="StatusPoller",
        model=model,
        instruction=(
            "You monitor an in-progress MTV migration.\n\n"
            "The migration details are in session state key 'migration_id'. "
            "Call `get_migration_status` with the MTV namespace to check "
            "current progress. Report the phase and completion status for "
            "each VM in the plan.\n\n"
            "If any VM shows errors, call `get_pod_logs` to fetch relevant "
            "forklift or virt-v2v logs. You may use `list_skills` and load "
            "the `mtv-log-analyzer` skill to diagnose failures.\n\n"
            "Output a status summary including: phase, VMs completed, "
            "VMs running, VMs failed, and any error details."
        ),
        tools=[get_migration_status, get_pod_logs, *skill_tools],
        output_key="migration_status",
    )

    monitor_checker = MigrationStatusChecker(name="StatusChecker")

    migration_monitor = LoopAgent(
        name="MigrationMonitor",
        sub_agents=[monitor_poller, monitor_checker],
        max_iterations=MONITOR_MAX_ITERATIONS,
    )

    # -- Phase 5: Validation -----------------------------------------------
    _post_template_hint = (
        f"The post-migration AAP job template ID is {POST_MIGRATION_TEMPLATE_ID}. "
        "Launch it via `launch_job(template_id)` with the VM hostname as extra_vars. "
        "Poll `get_job_status(job_id)` until complete, then retrieve the full "
        "output with `get_job_output(job_id)`. "
        if POST_MIGRATION_TEMPLATE_ID else
        "No POST_MIGRATION_TEMPLATE_ID is configured. Perform validation "
        "using MTV/KubeVirt APIs and skills only. "
    )

    validation_agent = LlmAgent(
        name="ValidationAgent",
        model=model,
        instruction=(
            "You validate that a completed migration produced correct results.\n\n"
            "The migration status is in session state key 'migration_status'. "
            "The original VM inventory is in session state key 'vm_inventory'.\n\n"
            "## AAP Post-Migration Validation\n"
            f"{_post_template_hint}"
            "Once you have the playbook output, load the `ansible-output-parser` "
            "skill and parse it. Use `load_skill_resource` to read "
            "`references/postmigration-task-map.md` for the task-to-category mapping.\n\n"
            "## OCP Virt Verification\n"
            "Also call `list_migrated_vms` in the target namespace and "
            "`get_vm_details` for each migrated VM. Compare against the source "
            "inventory in 'vm_inventory'.\n\n"
            "## Analysis\n"
            "From both AAP playbook results and OCP Virt data, verify:\n"
            "- Platform is OpenShift Virtualization\n"
            "- CPU/memory/network match pre-migration snapshot\n"
            "- ACM registration, vCenter cleanup, guest agent swap\n"
            "- CMDB updated, backup re-enrolled\n\n"
            "Load the `post-migration-validator` skill for the checklist.\n\n"
            "Output a validation report with:\n"
            "- Matches, Discrepancies, and overall verdict: PASS or FAIL"
        ),
        tools=[list_migrated_vms, get_vm_details, launch_job, get_job_status, get_job_output, *skill_tools],
        output_key="validation_result",
    )

    # -- Phase 6: Reporter -------------------------------------------------
    reporter_agent = LlmAgent(
        name="ReporterAgent",
        model=model,
        instruction=(
            "You generate formal migration completion reports.\n\n"
            "All previous data is available in session state:\n"
            "- 'vm_inventory': original VMware VM details\n"
            "- 'readiness_verdict': pre-migration assessment\n"
            "- 'migration_id': plan and migration names\n"
            "- 'migration_status': monitoring timeline and final status\n"
            "- 'validation_result': post-migration validation results\n\n"
            "Use `list_skills` and load the `completion-report-generator` skill "
            "for the report template and structure.\n\n"
            "Generate a comprehensive Markdown migration report that includes:\n"
            "1. Migration Summary (VM, source, target, hosting/hosted cluster, AZ)\n"
            "2. Before/After Comparison Table (CPU, memory, IP, guest agent)\n"
            "3. Pre-Migration Assessment Summary (from readiness_verdict)\n"
            "4. MTV Migration Timeline (from migration_status)\n"
            "5. Post-Migration Validation Results (from validation_result)\n"
            "6. MTV Log Analysis findings (if any)\n"
            "7. Outstanding Items and Remediation\n"
            "8. Sign-Off section\n\n"
            "After generating the report, call `save_report_artifact` with the "
            "full report content and filename 'migration-report.md' to save it "
            "as a downloadable artifact.\n\n"
        ),
        tools=[save_report_artifact, *skill_tools],
        output_key="final_report",
    )

    # -- Pipeline (SequentialAgent) ----------------------------------------
    migration_pipeline = SequentialAgent(
        name="MigrationPipeline",
        sub_agents=[
            discovery_agent,
            assessment_agent,
            migration_agent,
            migration_monitor,
            validation_agent,
            reporter_agent,
        ],
        description=(
            "Full VMware-to-OCP Virtualization migration workflow. "
            "Runs discovery, readiness assessment, migration execution, "
            "status monitoring, post-migration validation, and report "
            "generation as a deterministic sequential pipeline."
        ),
    )

    # -- Coordinator (root agent) ------------------------------------------
    coordinator_tools = [
        list_vmware_vms,
        list_migrated_vms,
        get_migration_status,
        get_vm_details,
        create_migration_plan,
        get_pod_logs,
        list_job_templates,
        launch_job,
        get_job_status,
        get_job_output,
        save_report_artifact,
        *skill_tools,
    ]

    coordinator = LlmAgent(
        name=AGENT_NAME,
        model=model,
        description=AGENT_DESC,
        instruction=_load_instruction(),
        sub_agents=[migration_pipeline],
        tools=coordinator_tools,
    )

    return coordinator


# ---------------------------------------------------------------------------
# Single mode: legacy monolithic agent (backward-compatible fallback)
# ---------------------------------------------------------------------------
_SINGLE_INSTRUCTION = (
    "You are an expert in VMware-to-OpenShift Virtualization migrations.\n\n"
    "## Operating Modes\n\n"
    "### Mode 1: With AAP (Live)\n"
    "When AAP is configured, trigger real Ansible job templates for pre-migration "
    "assessment and post-migration validation via AAP tools.\n\n"
    "### Mode 2: With Sample Data (Demo/Offline)\n"
    "When AAP is not available, or the user says 'analyze the sample output':\n"
    "- Pre-migration sample: `load_skill_resource` with skill `pre-migration-analyzer`, "
    "resource `references/samples/pre-migration-playbook-output.txt`\n"
    "- Post-migration sample: `load_skill_resource` with skill `post-migration-validator`, "
    "resource `samples/post-migration-playbook-output.txt`\n"
    "- Playbook YAML available at `references/samples/pre-migration-playbook.yml` and "
    "`references/samples/post-migration-playbook.yml`\n\n"
    "### Mode 3: User Pastes Output\n"
    "When the user pastes Ansible playbook output, analyze it using the "
    "`ansible-output-parser` skill and the appropriate analyzer skill.\n\n"
    "## Your Capabilities\n"
    "1. **Migration Readiness Assessment**: Discover VMware VMs, analyze their properties, produce readiness reports\n"
    "2. **Migration Execution**: Trigger MTV migrations from VMware to OCP Virt\n"
    "3. **Migration Monitoring**: Track progress, read logs, troubleshoot failures\n"
    "4. **Post-Migration Validation**: Verify migrated VMs match source, produce completion reports\n"
    "5. **Capacity Planning**: Analyze cluster capacity, plan batches, assess risk\n"
    "6. **Playbook Output Analysis**: Parse and analyze AAP playbook output (live or sample)\n\n"
    "## MTV / OCP Virt Tools\n"
    "- `list_vmware_vms(namespace)` -- List VMs on VMware vSphere via MTV inventory\n"
    "- `list_migrated_vms(namespace)` -- List VMs already on OCP Virtualization\n"
    "- `get_vm_details(namespace, vm_name)` -- Get detailed VM specification\n"
    "- `get_migration_status(namespace)` -- Check MTV migration plans and progress\n"
    "- `create_migration_plan(namespace, vm_name)` -- Trigger a real VMware-to-OCP Virt migration\n"
    "- `get_pod_logs(namespace, pod_pattern)` -- Read pod logs for troubleshooting\n\n"
    "## AAP Tools\n"
    "- `list_job_templates()` -- List available Ansible job templates\n"
    "- `launch_job(template_id)` -- Trigger an Ansible playbook via AAP\n"
    "- `get_job_status(job_id)` -- Check Ansible job progress\n"
    "- `get_job_output(job_id)` -- Retrieve playbook output\n\n"
    "## Skills (load on demand)\n"
    "- Use `list_skills` to discover available analysis skills\n"
    "- Use `load_skill` to get detailed instructions\n"
    "- Key skills: ansible-output-parser, pre-migration-analyzer, "
    "assessment-report-generator, post-migration-validator, "
    "completion-report-generator\n\n"
    "## Analyzing Playbook Output\n"
    "When asked to analyze pre-migration or post-migration output:\n"
    "1. Load the `ansible-output-parser` skill to parse the raw output\n"
    "2. Use `load_skill_resource` to read the appropriate task map\n"
    "3. Load the analyzer or validator skill for evaluation criteria\n"
    "4. Load the `assessment-report-generator` skill for report formatting\n"
    "5. Save the report using `save_report_artifact`\n\n"
    "## Standard Workflow\n"
    "When asked to assess a VM:\n"
    "1. Use `list_vmware_vms` to discover the VM on VMware\n"
    "2. Load the `pre-migration-analyzer` skill\n"
    "3. Analyze the VM properties\n"
    "4. Produce a readiness report using the `assessment-report-generator` skill\n\n"
    "When asked to migrate a VM:\n"
    "1. Use `create_migration_plan` to trigger the migration\n"
    "2. Poll `get_migration_status` to track progress\n"
    "3. When complete, use `list_migrated_vms` and `get_vm_details` to verify\n"
    "4. Produce a completion report using `completion-report-generator` skill\n\n"
    "Always explain what you're doing and why. Produce structured, actionable reports.\n"
    f"Default MTV namespace: {DEFAULT_MTV_NAMESPACE}. Default migrated VM namespace: {DEFAULT_VIRT_NAMESPACE}."
)


def _build_single_agent() -> LlmAgent:
    """Build the legacy single-agent (AGENT_MODE=single fallback)."""
    tools = []
    if skills:
        tools.append(SkillToolset(skills=skills))
    tools.extend([list_job_templates, launch_job, get_job_status, get_job_output])
    tools.extend([
        list_vmware_vms, list_migrated_vms, get_migration_status,
        get_vm_details, create_migration_plan, get_pod_logs,
        save_report_artifact,
    ])

    return LlmAgent(
        model=LiteLlm(model=ADK_MODEL),
        name=os.environ.get("AGENT_NAME", "migration_agent"),
        description=AGENT_DESC,
        instruction=_load_instruction(),
        tools=tools,
    )


# ---------------------------------------------------------------------------
# Coordinator instruction (pipeline mode)
# ---------------------------------------------------------------------------
_COORDINATOR_INSTRUCTION = (
    "You are the Migration Coordinator for VMware-to-OpenShift Virtualization migrations.\n\n"
    "## Operating Modes\n\n"
    "### Mode 1: With AAP (Live)\n"
    "When AAP is configured, you can trigger real Ansible job templates for pre-migration "
    "assessment and post-migration validation. Use `launch_job(template_id)` to trigger "
    "playbooks, `get_job_status(job_id)` to poll progress, and `get_job_output(job_id)` "
    "to retrieve the playbook output. Then analyze the output using skills.\n\n"
    "### Mode 2: With Sample Data (Demo/Offline)\n"
    "When AAP is not available, or the user says 'analyze the sample pre-migration output' "
    "or 'analyze the sample post-migration output', load the bundled sample data:\n"
    "- Use `load_skill_resource` with skill `pre-migration-analyzer` and resource "
    "`references/samples/pre-migration-playbook-output.txt` for pre-migration sample output\n"
    "- Use `load_skill_resource` with skill `post-migration-validator` and resource "
    "`references/samples/post-migration-playbook-output.txt` for post-migration sample output\n"
    "- The sample playbook YAML is also available at `references/samples/pre-migration-playbook.yml` "
    "and `samples/post-migration-playbook.yml` for reference\n\n"
    "### Mode 3: User Pastes Output\n"
    "When the user pastes Ansible playbook output directly in chat, analyze it using "
    "the `ansible-output-parser` skill and the appropriate analyzer/validator skill.\n\n"
    "## Delegation Rules\n"
    "- **Full migration workflow**: When the user asks to migrate a VM or run a full "
    "migration, delegate to `MigrationPipeline`. It will automatically run discovery, "
    "assessment, migration, monitoring, validation, and reporting as a sequential pipeline.\n"
    "- **Individual queries**: For standalone questions (list VMs, check status, read logs, "
    "run Ansible jobs, analyze output), use your own tools directly without delegating.\n\n"
    "## Your Direct Tools\n"
    "- `list_vmware_vms(namespace)` -- Discover VMware VMs via MTV inventory\n"
    "- `list_migrated_vms(namespace)` -- List VMs on OCP Virtualization\n"
    "- `get_vm_details(namespace, vm_name)` -- Detailed VM spec\n"
    "- `get_migration_status(namespace)` -- Check MTV plan/migration progress\n"
    "- `create_migration_plan(namespace, vm_name)` -- Trigger migration\n"
    "- `get_pod_logs(namespace, pod_pattern)` -- Read pod logs\n"
    "- `list_job_templates()` / `launch_job(template_id)` / `get_job_status(job_id)` / "
    "`get_job_output(job_id)` -- AAP Ansible automation\n"
    "- `save_report_artifact(report_content, filename)` -- Save report as downloadable artifact\n\n"
    "## Skills (load on demand)\n"
    "- Use `list_skills` to discover analysis skills\n"
    "- Use `load_skill` to get step-by-step instructions\n"
    "- Key skills: pre-migration-analyzer, ansible-output-parser, "
    "assessment-report-generator, post-migration-validator, "
    "completion-report-generator, mtv-log-analyzer, "
    "capacity-analyzer, risk-assessor, batch-planner\n\n"
    "## Analyzing Playbook Output\n"
    "When asked to analyze pre-migration or post-migration output:\n"
    "1. Load the `ansible-output-parser` skill to parse the raw output\n"
    "2. Use `load_skill_resource` to read the appropriate task map "
    "(`references/premigration-task-map.md` or `references/postmigration-task-map.md`)\n"
    "3. Load the `pre-migration-analyzer` or `post-migration-validator` skill for "
    "domain-specific evaluation criteria\n"
    "4. Load the `assessment-report-generator` skill to format the final report\n"
    "5. Save the report using `save_report_artifact`\n\n"
    "## Defaults\n"
    f"- MTV namespace: {DEFAULT_MTV_NAMESPACE}\n"
    f"- Migrated VM namespace: {DEFAULT_VIRT_NAMESPACE}\n\n"
    "Always explain what you're doing. Produce structured, actionable output."
)


# ---------------------------------------------------------------------------
# Build root_agent based on AGENT_MODE
# ---------------------------------------------------------------------------
log.info("Agent mode: %s", AGENT_MODE)

if AGENT_MODE == "single":
    log.info("Building legacy single-agent architecture")
    root_agent = _build_single_agent()
else:
    log.info("Building multi-agent pipeline architecture")
    root_agent = _build_pipeline_agent()

log.info("Root agent ready: %s", root_agent.name)
