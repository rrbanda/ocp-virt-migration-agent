---
name: assessment-report-generator
description: >-
  Generates formal migration readiness assessment reports from AAP pre-migration
  playbook output. Produces executive summaries, detailed findings per check
  category, remediation steps, and migration recommendations. Structured around
  the real pre-migration checks: hypervisor, OS, kernel/boot, disk, network,
  packages, backup, and CMDB validation.
---

# Assessment Report Generator Instructions

When given parsed pre-migration playbook results (from the ansible-output-parser
skill), generate a formal migration readiness assessment report.

Use `load_skill_resource` to read `references/report-template.md` for formatting
guidelines and severity definitions.

## Report Structure

### 1. Executive Summary
- VM hostname and environment
- Overall readiness verdict: READY / NOT READY / NEEDS REVIEW
- Migration risk: LOW / MEDIUM / HIGH
- Number of blockers and warnings
- Recommended action: Proceed / Remediate / Escalate

### 2. VM Profile
Present as a table:
| Property | Value |
|----------|-------|
| Hostname | (from playbook host) |
| OS | (distribution + version from "Operating System" task) |
| CPU | (vCPUs from "CPU and Memory" task) |
| Memory | (MB from "CPU and Memory" task) |
| Disk Layout | (mount points + free space from "Mount points" task) |
| Network | (interfaces + IPs from "Network Interfaces" task) |
| Current Platform | VMware (from "Assert VM is on VMware") |
| Target Platform | OpenShift Virtualization |

### 3. Readiness Checklist

For each category, report PASS / FAIL / WARNING with details from the playbook:

**Hypervisor** (from: Assert VM is on VMware)
**Operating System** (from: Verify Valid OS)
**Kernel & Boot** (from: grub consistency check, grubenv size, kernel package match)
**RPM Database** (from: rpmdb_fix.sh output)
**Disk & Filesystem** (from: fstab check, boot flag, crypt check, augtool, free space)
**Package Readiness** (from: qemu-guest-agent installability, selinux-policy)
**NFS / Remote Filesystem** (from: NFS mount detection, remote-fs.target)
**Backup** (from: Netbackup bpclimagelist check)
**CMDB / Lifecycle** (from: Assert VM is not Decommissioning)
**Timezone** (from: LocalRTC check for PDT)

### 4. Blockers (if any)
For each FAIL result:
- **Issue**: What failed (exact task name and error)
- **Impact**: Why this blocks migration
- **Remediation**: Specific steps to fix
- **Owner**: Which team should fix (OS Team, Storage Team, App Team, etc.)

### 5. Warnings (if any)
For each WARNING or ignored error:
- **Issue**: What was flagged
- **Risk**: What could go wrong during migration
- **Recommendation**: Suggested action before or after migration

### 6. Recommendations
- Whether to proceed with migration
- Pre-migration remediation steps in priority order
- Estimated remediation effort
- Suggested migration window
