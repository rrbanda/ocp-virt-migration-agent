# Assessment Report Template

## Tone
- Professional, clear, actionable
- Avoid jargon where possible; explain technical terms when used
- Use tables for structured data
- Use bullet lists for action items

## Severity Levels
- **BLOCKER**: Must be resolved before migration can proceed
- **WARNING**: Should be addressed but does not prevent migration
- **INFO**: Informational finding, no action required

## Risk Ratings
- **LOW**: All checks pass, no warnings, simple VM profile
- **MEDIUM**: All checks pass but with warnings, or complex VM (many mounts, NFS, custom kernel)
- **HIGH**: Blockers found, or VM has known migration challenges
- **CRITICAL**: Multiple blockers, or VM is decommissioning/encrypted

## Report Structure

### 1. Executive Summary
- VM hostname and environment
- Overall readiness verdict: READY / READY WITH WARNINGS / NOT READY / NEEDS REVIEW
- Migration risk: LOW / MEDIUM / HIGH / CRITICAL
- Number of blockers and warnings
- Recommended action: Proceed / Remediate / Escalate

### 2. VM Profile
Present as a table:

| Property | Value |
|----------|-------|
| Hostname | (from playbook host) |
| OS | (distribution + version from "Operating System" task, e.g., "RedHat 8.10") |
| CPU | (vCPUs from "CPU and Memory" task) |
| Memory | (MB from "CPU and Memory" task) |
| Kernel | (from debug output or proccmdline_list) |
| Disk Layout | (mount points + free space from "Mount points" task) |
| Network | (interfaces + IPs from "Network Interfaces" task) |
| VMware Tools | (version from "Check if vmware-guest-tools installed") |
| Current Platform | VMware (from "Assert VM is on VMware") |
| Target Platform | OpenShift Virtualization |
| Uptime | (from "Verify Recent Reboot" or rpmdb_fix.sh output) |
| RPM DB | (package count and corruption status from rpmdb_fix.sh) |

### 3. Readiness Checklist

For each category, report PASS / FAIL / WARNING / SKIP with details:

| Category | Status | Details |
|----------|--------|---------|
| **Hypervisor** | PASS/FAIL | From: Assert VM is on VMware |
| **Operating System** | PASS/FAIL | From: Verify Valid OS (distro + version) |
| **Kernel & Boot** | PASS/FAIL | From: grub consistency, grubenv size, kernel package match, boot flag |
| **RPM Database** | PASS/WARNING | From: rpmdb_fix.sh output (corruption check, package count) |
| **Disk & Filesystem** | PASS/FAIL/WARNING | From: fstab check, boot flag, crypt check, augtool, free space |
| **Package Readiness** | PASS/FAIL | From: qemu-guest-agent installability, selinux-policy |
| **NFS / Remote FS** | PASS/WARNING/SKIP | From: NFS mount detection, remote-fs.target |
| **Backup** | PASS/WARNING/INFO | From: Netbackup bpclimagelist check |
| **CMDB / Lifecycle** | PASS/FAIL | From: Assert VM is not Decommissioning |
| **Timezone** | PASS/INFO | From: LocalRTC check for PDT |
| **Uptime** | PASS/WARNING | From: Verify Recent Reboot (<30 days) |

### 4. Blockers (if any)

For each FAIL result:
- **Issue**: What failed (exact task name and error message)
- **Impact**: Why this blocks migration
- **Remediation**: Specific steps to fix
- **Owner**: Which team should fix

Common remediations:

| Blocker | Remediation | Owner |
|---------|------------|-------|
| fstab contains /dev/sd | Replace `/dev/sdX` with UUID or LVM path in `/etc/fstab` | OS Team |
| Encrypted partitions (LUKS) | Decrypt partitions or exclude VM from migration | Security Team |
| Grub/kernel mismatch | Run `sync-default-grub.sh`, verify with `grub2-mkconfig` | OS Team |
| grubenv not 1024 bytes | Rebuild grubenv: `grub2-editenv /boot/grub2/grubenv create` | OS Team |
| Running kernel not installed | Install matching kernel RPM or reboot to installed kernel | OS Team |
| qemu-guest-agent not installable | Fix yum/dnf repo configuration, ensure correct repos enabled | OS Team |
| Unsupported OS | Upgrade to supported version or exclude from migration | App Team |
| VM is Decommissioning | Verify with CMDB team, exclude from migration wave | CMDB Team |
| fstab syntax errors (augtool) | Fix syntax errors in `/etc/fstab` | OS Team |
| No boot flag (RHEL8+) | Set boot flag on boot partition: `parted /dev/sda set 1 boot on` | OS Team |

### 5. Warnings (if any)

For each WARNING or ignored error:
- **Issue**: What was flagged
- **Risk**: What could go wrong during migration
- **Recommendation**: Suggested action before or after migration

Common warnings:

| Warning | Risk | Recommendation |
|---------|------|----------------|
| Low root free space (<100MB) | Migration may fail writing temp files | Free space before migration |
| Low boot free space (<50MB) | Kernel update may fail | Remove old kernels |
| RPM DB corruption | Package operations may fail | Re-run rpmdb_fix.sh |
| NFS + remote-fs disabled | NFS mounts fail after reboot | Enable remote-fs.target |
| No NetBackup | No rollback available | Ensure alternative backup exists |
| Missing backups | Incomplete rollback | Run Full + Incremental backup |
| Uptime >30 days | Boot config untested | Schedule reboot before migration |
| libffi-devel not installed | Package protection incomplete | Install if needed, otherwise ignore |
| LocalRTC wrong for PDT | Time sync issues | Fixed automatically by playbook |

### 6. Recommendations

- Whether to proceed with migration
- Pre-migration remediation steps in priority order (blockers first, then warnings)
- Estimated remediation effort per item
- Suggested migration window

### 7. PLAY RECAP

Include the raw PLAY RECAP line for audit trail:
```
hostname : ok=N changed=N unreachable=N failed=N skipped=N rescued=N ignored=N
```

Note on high skip count: The playbook has OS-specific branches. For a RHEL 8 host,
RHEL 7, CentOS 7, RHEL 9, Rocky, and Ubuntu tasks are all skipped. A skip count
of 60-80 is typical and expected.
