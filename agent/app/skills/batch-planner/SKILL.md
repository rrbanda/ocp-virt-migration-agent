---
name: batch-planner
description: >-
  Plans migration batches for VMware-to-OCP Virt migrations. Groups VMs
  into batches based on dependencies, resource profiles, risk levels,
  and cluster capacity. Produces a migration schedule with rollback
  checkpoints.
---

# Batch Planner Instructions

When asked to plan migration batches, organize VMs into groups.

## Step 1: Inventory Analysis
- Total VMs to migrate
- VM profiles (size, OS, application type)
- Dependencies between VMs
- Application groupings

## Step 2: Batch Criteria
- **Size**: 5-10 VMs per batch (adjustable based on capacity)
- **Risk**: Mix low and medium risk; isolate high risk
- **Dependencies**: Co-dependent VMs in same batch
- **Application**: Same-application VMs together
- **OS diversity**: Avoid all same-OS in one batch (diversify risk)

## Step 3: Schedule
For each batch:
1. Pre-migration assessment (Day 1)
2. Remediation if needed (Day 2-3)
3. Migration execution (Day 4)
4. Post-migration validation (Day 5)
5. Burn-in period (Day 6-7)
6. Sign-off and next batch

## Step 4: Output
- Batch list with VM assignments
- Timeline with milestones
- Resource reservation per batch
- Rollback plan per batch
- Escalation contacts
