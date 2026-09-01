---
name: production-migration-planner
description: >-
  Plans and manages multi-wave production VMware-to-OpenShift Virtualization
  migrations. Covers dependency mapping, wave grouping, change management
  windows, go/no-go criteria, rollback procedures, production cutover steps,
  and post-wave validation. Designed for enterprise infrastructure teams
  running migration programs at scale.
---

# Production Migration Planner

Help the user plan a structured, enterprise-grade migration program for
moving VMware VMs to OpenShift Virtualization in production.

## Step 1: Inventory and Dependencies

Before planning waves, map the full VM estate:

1. Use `list_vmware_vms` to get the complete inventory
2. Ask the user to identify **application groups** (VMs that must migrate together)
3. Map dependencies:
   - Database + application server: same wave
   - Load balancer: migrate last (or use external LB during transition)
   - Shared services (DNS, AD, NFS): keep on VMware until all dependents migrate

Read `references/dependency-mapping.md` for common patterns.

## Step 2: Wave Planning

Group VMs into migration waves using the `batch-planner` and `risk-assessor` skills.

Production wave sizing:
- **5-10 VMs per wave** for initial waves (lower risk)
- **10-20 VMs per wave** once the team gains confidence
- **Never more than 20 VMs** in a single change window

Wave ordering principles:
1. **Wave 0**: Non-production / dev-test VMs (practice run)
2. **Wave 1-2**: Low-risk production VMs (simple OS, no NFS, verified backup)
3. **Wave 3-N**: Medium-risk VMs (larger disks, more dependencies)
4. **Final wave**: High-risk / critical VMs (databases, AD-integrated, complex networking)

Read `references/wave-planning.md` for detailed guidance.

## Step 3: Change Management

For each wave, produce a change management package:

1. **Change Request**: Summary, risk level, rollback plan, affected services
2. **Communication Plan**: Who needs to know, when, what they need to do
3. **Pre-wave Go/No-Go Checklist**: All checks that must pass before starting
4. **Execution Runbook**: Step-by-step procedure for the migration team
5. **Post-wave Validation**: What to check in the first 24 hours

Read `references/change-management.md` for templates.

## Step 4: Go/No-Go Criteria

Before each wave, verify:

| Check | Owner | Blocker? |
|-------|-------|----------|
| All VMs in wave have verified backup | Backup team | Yes |
| Cluster pre-flight passes | Platform team | Yes |
| Change request approved by CAB | Change mgmt | Yes |
| DNS updates prepared (not applied) | Network team | Yes |
| Rollback procedure tested | Migration team | Yes |
| Monitoring configured for target VMs | Ops team | Recommended |
| Communication sent to stakeholders | Project lead | Yes |

Read `references/go-nogo-criteria.md` for the full checklist.

## Step 5: Rollback Procedures

If a wave fails:

1. **Per-VM rollback**: Use `rollback_migration` tool to clean up MTV CRs, restart source VM on VMware
2. **Per-wave rollback**: Roll back all VMs in the wave, revert DNS changes, notify stakeholders
3. **Decision criteria**: Rollback if > 20% of VMs in the wave fail, or any critical VM fails

Read `references/rollback-procedures.md` for step-by-step instructions.

## Step 6: Production Cutover

After MTV migration completes and validation passes:

1. Update DNS records to point to new OCP Virt VM IPs
2. Update load balancer pools
3. Update monitoring to watch new VMs
4. Decommission source VMs on VMware (rename, disconnect NICs, power off)
5. Update CMDB records

Read `references/production-cutover.md` for the cutover runbook.

## Step 7: Post-Wave Validation

In the 24 hours after each wave:

1. Verify all VMs are running and accessible
2. Compare CPU/memory/network with pre-migration baselines
3. Monitor application logs for errors
4. Validate backup enrollment on new platform
5. Collect feedback from application owners

Use the `post-migration-validator` skill for automated validation.

## Step 8: Output

Produce a migration program document including:
1. Full VM inventory with wave assignments
2. Wave schedule with change windows
3. Per-wave go/no-go checklists
4. Rollback procedures
5. Communication plan
6. Risk register

Save with `save_report_artifact` as `migration-program-plan.md`.
