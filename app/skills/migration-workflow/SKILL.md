---
name: migration-workflow
description: >-
  End-to-end VMware-to-OCP Virt migration workflow orchestrator. Chains the
  complete sequence: discovery, readiness assessment, migration type selection
  (cold, warm, or live), execution, real-time monitoring, post-migration
  validation, and completion reporting. Supports MTV 2.8+ warm migration (GA)
  and MTV 2.10+ cross-cluster live migration.
  Use this skill when asked to run a full migration for a VM.
---

# Migration Workflow Orchestrator

When asked to run a full migration workflow for a VM, execute these phases in order.
Do NOT skip phases. Report results at each phase before proceeding.

## Migration Types (MTV 2.8+)

MTV supports three migration types. Select the appropriate type based on requirements:

| Type | GA Since | VM State During Transfer | Downtime | Best For |
|------|----------|--------------------------|----------|----------|
| **Cold** | MTV 2.0 | Powered off | Full duration of disk copy | Small disks, maintenance windows available |
| **Warm** | MTV 2.8 | Running (CBT incremental copies) | Only during final cutover (minutes) | Large disks, minimal downtime needed |
| **Live** | MTV 2.10 | Running on OCP Virt source cluster | Near-zero | Cross-cluster moves between OCP Virt clusters (requires OCP Virt 4.20+) |

## Phase 1: DISCOVER

1. Call `list_vmware_vms(namespace)` to find the target VM in VMware inventory
2. Confirm the VM exists and extract: name, CPU, memory, OS, disk size, firmware, power state, networks
3. If VM not found: STOP and report error

## Phase 2: ASSESS

1. Load the `pre-migration-analyzer` skill
2. Analyze the VM properties against the readiness criteria
3. Produce a readiness verdict: READY / NOT READY / NEEDS REVIEW
4. If NOT READY: STOP and report blockers with remediation steps
5. If READY: report the assessment summary and proceed

## Phase 3: SELECT MIGRATION TYPE

Based on the assessment and user requirements, recommend a migration type:

### Cold Migration (default)
- VM is powered off for the entire transfer
- Most reliable; works for all source types (VMware, RHV, OpenStack, OVA)
- Use when: maintenance window is available, VM can tolerate full downtime

### Warm Migration (VMware and RHV sources only)
- VM stays running; MTV uses Changed Block Tracking (CBT) for incremental disk copies
- Only the final cutover requires downtime (typically minutes)
- **Prerequisites (all must be met):**
  - CBT must be enabled on the VM AND on each individual disk in vCenter
  - VDDK image configured in MTV (required for CBT snapshots)
  - Maximum 32 CBT snapshots per VM (MTV creates snapshots at 1-hour intervals by default; configurable via `SNAPSHOT_INTERVAL` in forklift-controller)
  - VM must NOT be hibernated/suspended
  - If migrating >10 VMs from a single ESXi host, increase NFC service memory on that host
- **Cutover options:**
  - Manual: user triggers cutover via console or API when ready
  - Scheduled: set `cutover` timestamp in the `Migration` manifest

### Live Migration (OCP Virt to OCP Virt only, MTV 2.10+)
- Zero-downtime migration between two OpenShift Virtualization clusters
- Requires OCP Virt 4.20+ on both source and target clusters
- Not applicable for VMware-to-OCP migrations

### OVA Import (MTV 2.11.1+ GA)
- Import VMs directly from local OVA files without a VMware provider
- No vCenter connectivity required
- Useful when VMs have already been exported or when source vSphere is decommissioned

## Phase 3.5: DEEP INSPECTION (Optional, MTV 2.12 Tech Preview)

Before migrating, optionally run Deep Inspection to analyze disk images and detect:
- Guest OS compatibility issues
- Missing VirtIO drivers
- File system errors
- CBT configuration problems

This is a Technology Preview feature. MTV processes inspections in batches of 10 concurrent operations.

## Phase 4: CREATE MIGRATION PLAN

1. Call `create_migration_plan(namespace, vm_name, plan_name, target_namespace, warm)` to create:
   - NetworkMap CR (source network name -> destination NAD or pod network)
   - StorageMap CR (datastore -> StorageClass)
   - Plan CR (VMs + mappings + warm/cold flag)
2. The function waits for Plan validation (Ready:True) and returns plan details for review
3. **Present the plan to the user for HITL review** before proceeding:
   - VM specs (CPU, memory, disks, OS, firmware, power state)
   - Network mappings
   - Storage class
   - Migration type (cold/warm)
   - Plan validation status
4. If plan validation fails: report the error and STOP

## Phase 4.5: EXECUTE MIGRATION (after human approval)

1. Call `execute_migration(namespace, plan_name, cutover)` to create the Migration CR
   - For cold migration: leave cutover empty
   - For warm migration with scheduled cutover: provide RFC 3339 timestamp (e.g., `2025-03-15T02:00:00Z`)
2. Report: "Migration started. Plan: [name], Type: [cold/warm]"
3. If execution fails: report the error and STOP

## Phase 5: MONITOR

1. Call `get_migration_status(namespace)` to check progress
2. Report the current phase and any VM-level progress
3. **For cold migration:** wait 15-20 seconds between checks
4. **For warm migration:**
   - Monitor incremental copy cycles (each ~1 hour by default)
   - Report snapshot count (warn if approaching the 32-snapshot limit)
   - When incremental copies are caught up, prompt user for cutover (or wait for scheduled cutover)
   - After cutover: monitor final transfer and VM power-off on source
5. Repeat until migration is complete (Succeeded) or failed
6. During monitoring, optionally call `get_pod_logs("openshift-mtv", "forklift")` to check for issues
7. If failed: call `get_pod_logs` for error details, load `mtv-log-analyzer` skill for diagnosis

## Phase 6: VALIDATE

1. Call `validate_migrated_vm(target_namespace, vm_name)` for comprehensive automated checks:
   - VirtualMachineInstance status (Running?)
   - QEMU guest agent connected (AgentConnected condition)
   - PVC bound and capacity matches source
   - CPU/memory matches source specs
   - Network interfaces present
2. Also call `get_vm_details(target_namespace, vm_name)` for detailed spec comparison
3. Production validation checklist (per Red Hat docs):
   - VM boot completion (OS prompt available, no kernel panic)
   - Network connectivity (ping gateway and DNS from inside VM)
   - Persistent volume mount (all expected volumes mounted with correct size)
   - VirtIO driver status (VirtIO disk and network adapters present)
   - Time sync (NTP synchronized, offset < 100ms)
   - Application health (service responds within SLA)
   - Source VM power state maintained (powered off after cold migration)
4. Report any discrepancies

## Phase 7: REPORT

1. Load the `completion-report-generator` skill
2. Produce a formal migration completion report including:
   - Source VM details (from Phase 1)
   - Readiness assessment (from Phase 2)
   - Migration type used and rationale (from Phase 3)
   - Migration timeline (from Phase 5)
   - Validation results (from Phase 6)
   - Overall status: COMPLETE / PARTIAL / FAILED

## Error Handling

- If any phase fails, do NOT proceed to the next phase
- Report the failure clearly with the error details
- Suggest remediation steps
- If migration was triggered but monitoring shows failure, still proceed to Phase 6 and 7 to document the failure

### Warm Migration Specific Errors
- **`Warm import retry limit reached`**: VM exceeded 32 CBT snapshots. Cancel, consolidate snapshots, restart.
- **CBT not enabled**: Enable CBT on VM and each disk in vCenter, then retry.
- **ESXi NFC memory exhaustion**: Too many concurrent warm migrations from one host. Reduce concurrency or increase NFC service memory.
