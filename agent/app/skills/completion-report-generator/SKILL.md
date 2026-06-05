---
name: completion-report-generator
description: >-
  Generates migration completion reports combining MTV migration timeline,
  AAP pre-migration assessment, and AAP post-migration validation results.
  Produces a formal record with before/after comparison, vCenter cleanup
  confirmation, ACM registration, CMDB update, and sign-off checklist.
---

# Completion Report Generator Instructions

When given both pre-migration and post-migration results (from ansible-output-parser),
plus MTV migration status data, generate a formal migration completion report.

## Report Structure

### 1. Migration Summary
- VM hostname
- Source: VMware vCenter
- Target: OpenShift Virtualization cluster (hosting + hosted cluster from ACM)
- Availability Zone (extracted from post-migration playbook)
- Migration status: COMPLETE / PARTIAL / FAILED
- Migration date
- MTV plan name and migration name
- Total migration duration (from MTV status)

### 2. Before/After Comparison Table
| Property | Before (VMware) | After (OCP Virt) | Match |
|----------|----------------|-------------------|-------|
| Platform | VMware | OpenShift Virtualization | Expected |
| OS | (from pre-migration facts) | (from post-migration facts) | Must match |
| CPU vCPUs | (from pre-migration) | (from post-migration) | Must match exactly |
| Memory MB | (from pre-migration) | (from post-migration) | Within 10% |
| IP Address | (from pre-migration) | (from post-migration) | Must match |
| Netmask | (from pre-migration) | (from post-migration) | Must match |
| Gateway | (from pre-migration) | (from post-migration) | Must match |
| Guest Agent | vmware-tools | qemu-guest-agent | Expected swap |

### 3. Pre-Migration Assessment Summary
- Readiness verdict at time of migration
- Any warnings that were accepted
- Remediation actions taken before migration

### 4. MTV Migration Timeline
- Plan creation time
- Migration start time
- Disk transfer progress checkpoints
- Migration completion time
- Total duration
- Any retries or errors during transfer

### 5. Post-Migration Validation Results

**Platform Verification**: OSV platform confirmed
**Fact Comparison**: CPU, memory, network match pre-migration snapshot
**ACM Registration**: VM found in ACM, hosting/hosted cluster identified
**vCenter Cleanup**:
  - VM renamed in vCenter
  - NICs disconnected
  - VM powered off
**Guest Agent**: VMware tools removed, qemu-guest-agent installed and running
**CMDB Updated**: Hosting cluster, hosted cluster, AZ, RC Console written
**Backup**: Re-enrolled if required (based on backupRequired flag)

### 6. MTV Log Analysis (if applicable)
- Any errors or warnings from forklift-controller logs
- virt-v2v conversion notes
- KB articles referenced or created

### 7. Outstanding Items
- Any warnings or issues from post-migration that need follow-up
- Timeline for resolution
- Assigned team/owner

### 8. Sign-Off
- Migration Engineer: (name)
- Date: (current date)
- Status: APPROVED / PENDING REVIEW
