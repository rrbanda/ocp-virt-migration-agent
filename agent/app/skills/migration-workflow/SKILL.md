---
name: migration-workflow
description: >-
  End-to-end VMware-to-OCP Virt migration workflow orchestrator. Chains the
  complete sequence: discovery, readiness assessment, migration execution,
  real-time monitoring, post-migration validation, and completion reporting.
  Use this skill when asked to run a full migration for a VM.
---

# Migration Workflow Orchestrator

When asked to run a full migration workflow for a VM, execute these phases in order.
Do NOT skip phases. Report results at each phase before proceeding.

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

## Phase 3: MIGRATE

1. Confirm with the user: "VM [name] is ready. Proceeding with migration."
2. Call `create_migration_plan(namespace, vm_name)` to trigger the migration
3. Report: "Migration triggered. Plan: [name], Migration: [name]"
4. If creation fails: report the error and STOP

## Phase 4: MONITOR

1. Call `get_migration_status(namespace)` to check progress
2. Report the current phase and any VM-level progress
3. If still running: wait 15-20 seconds, then check again
4. Repeat until migration is complete (Succeeded) or failed
5. During monitoring, optionally call `get_pod_logs("openshift-mtv", "forklift")` to check for issues
6. If failed: call `get_pod_logs` for error details, load `mtv-log-analyzer` skill for diagnosis

## Phase 5: VALIDATE

1. Call `list_migrated_vms(target_namespace)` to find the newly migrated VM
2. Call `get_vm_details(target_namespace, vm_name)` to get full specification
3. Compare with source VM properties from Phase 1:
   - CPU cores match?
   - Memory approximately matches?
   - Disk count matches?
   - VM is in expected status?
4. Report any discrepancies

## Phase 6: REPORT

1. Load the `completion-report-generator` skill
2. Produce a formal migration completion report including:
   - Source VM details (from Phase 1)
   - Readiness assessment (from Phase 2)
   - Migration timeline (from Phase 4)
   - Validation results (from Phase 5)
   - Overall status: COMPLETE / PARTIAL / FAILED

## Error Handling

- If any phase fails, do NOT proceed to the next phase
- Report the failure clearly with the error details
- Suggest remediation steps
- If migration was triggered but monitoring shows failure, still proceed to Phase 5 and 6 to document the failure
