---
name: migration-history-lookup
description: >-
  Answers questions about past migrations by checking the live cluster first.
  Use when asked "when was X migrated", "was X migrated", "show migration history",
  or any question about completed migrations. Always prioritize live cluster data
  over session-scoped history.
---

# Migration History Lookup

When the user asks about past or completed migrations, always check the **live cluster first**.
Session history is supplementary and may be empty after a pod restart.

## Step 1: Check the live cluster (always do this first)

1. Call `list_migrated_vms(namespace="{virt_namespace}")` to see all VMs that have been migrated to OpenShift Virtualization
2. For a specific VM, call `get_vm_details(namespace="{virt_namespace}", vm_name="<vm>")` to get:
   - `creationTimestamp` — this is when the migration completed
   - CPU, memory, disk, network configuration
   - Current running status
   - Labels (including migration metadata from Forklift)

## Step 2: Check MTV migration records

Call `get_migration_status(namespace="{mtv_namespace}")` to see:
- Plan CRs: whether they succeeded, failed, or are still executing
- Migration CRs: when they were created (start time) and current phase
- VM-level progress: completed, running, or failed counts

This gives you the migration timeline: Plan creation → Migration start → Completion.

## Step 3: Check session history (supplementary only)

Call `search_migration_history(query)` for any notes recorded during this session.
This only has data from the **current session** — it will be empty after a pod restart.
Do not rely on this as the primary source.

## Key principle

The live cluster is the **source of truth** for migration history. Use `list_migrated_vms`,
`get_vm_details`, and `get_migration_status` to answer history questions. Use
`search_migration_history` only as a supplement.
