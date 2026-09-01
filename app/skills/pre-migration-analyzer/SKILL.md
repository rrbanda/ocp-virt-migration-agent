---
name: pre-migration-analyzer
description: >-
  Analyzes pre-migration playbook output for VMware-to-OpenShift Virtualization
  readiness. Evaluates 36 checks across 11 categories derived from the customer's
  actual Ansible playbook: hypervisor, OS, kernel/boot, RPM database, disk/filesystem,
  packages, NFS/remote-fs, backup, CMDB, timezone, and uptime. Produces a
  migration readiness verdict with categorized findings and specific remediation.
---

# Pre-Migration Analyzer Instructions

When given pre-migration playbook output (raw AAP output or pasted text), analyze
the VM's readiness for VMware-to-OpenShift Virtualization migration.

## Step 1: Load References

Read `references/pre-migration-checklist.md` for the full list of 36 checks
with exact task names, pass criteria, and failure impact.

If the user says "analyze the sample pre-migration output" (or similar), load
the bundled sample from `references/samples/pre-migration-playbook-output.txt`.

## Step 2: Identify the Host and OS

From the output, extract:
- **Hostname**: from the `ok: [hostname]` lines
- **OS**: from the `Operating System` task (e.g., "RedHat 8.10")
- **CPU**: from `CPU and Memory` task (e.g., "cpu: 4, memory_mb: 15729")
- **Network**: from `Network Interfaces` task

Use the OS to determine which kernel/package branch was active (RHEL7, RHEL8/9,
Rocky8/9, CentOS7, or Ubuntu). All tasks from other branches should be marked
as SKIP (expected).

## Step 3: Evaluate Each Category

### 3.1 Hypervisor Verification
- `Identify current hypervisor`: must be `changed` (dmidecode ran)
- `Assert VM is on VMware`: must be `ok` with "All assertions passed"
- If either fails: **BLOCKER**

### 3.2 Operating System
- `Operating System`: info only, extract distro + version
- `Verify Valid OS`: must be `ok` -- supported: RHEL 7/8/9, CentOS 7, Rocky 8/9, Ubuntu 20/22
- If unsupported: **BLOCKER**

### 3.3 Kernel & Boot Configuration
- `Read in /proc/cmdline`: must be `ok`
- `Read in grub2-mkconfig and get output`: must be `changed`
- `Ensure that when v2v generates new grub the kernel args match`: **CRITICAL** -- `proccmdline_list` must have zero difference from `grubgen_list`
- `Assert running kernel is installed package`: must be `ok`
- `grubenv is exactly 1024 bytes`: must be `ok`
- `Check partitions for bootflag`: must show stdout "1" (RHEL8+ only)
- `Sync Default Grub` block (if ran): means params diverged and were fixed
- If kernel/grub mismatch: **BLOCKER** -- VM will not boot after migration

### 3.4 RPM Database
- `Execute rpmdb_fix.sh`: check stdout for "RPMDB not corrupted" and package count
- Look for: uptime, hung processes count, var filesystem usage, rebuild status
- If corrupted: **WARNING** (remediation: re-run rpmdb_fix.sh)

### 3.5 Disk & Filesystem
- `Verify fstab does not contain /dev/sd`: must be `ok` (no changes) -- if changed, fstab has /dev/sd entries: **BLOCKER**
- `Augtool check fstab for errors`: stdout must be "0" -- if non-zero: **BLOCKER**
- `Check partitions for crypt`: stdout must be "0" -- if non-zero: **BLOCKER** (encryption not supported)
- `Check partitions for bootflag`: stdout must be "1" (RHEL8+)
- `Root mount point freespace > 100MB`: must be `ok` per mount -- if failed: **WARNING**
- `Boot mount point freespace > 50MB`: must be `ok` per mount -- if failed: **WARNING**
- `Other mount point freespace > 10MB`: must be `ok` per mount (excludes /, /boot, loop, sys, run, nfs, cifs, fuse, autofs) -- if failed: **WARNING**
- `Execute check-filesystem-usage.ksh`: review stdout for usage warnings

### 3.6 Package Readiness
- `Check if qemu-guest-agent can be installed by MTV`: must be `changed`/`ok` -- if failed: **BLOCKER** (fix repos)
- `Ensure selinux-policy-targeted installed`: must be `ok`/`changed`
- `Protect packages from autoremove`: some items may fail for uninstalled packages (`ignore_errors`) -- this is expected, not a failure
- `Check if vmware-guest-tools installed`: `changed` confirms VMware tools present (will be removed post-migration)

### 3.7 NFS / Remote Filesystem
- `Detect active nfs mount`: rc=0 means NFS present
- `Check if system has NFS mount (is-enabled)`: conditional on NFS detection
- `Assert remote-fs is enabled if there are NFS mounts`: if NFS present but remote-fs disabled: **WARNING**
- If no NFS (skipping): PASS -- no action needed

### 3.8 Backup (NetBackup)
- `Run Netbackup tool`: `changed` with rc=0 means NBU present; `fatal` with rc=127 means no NBU -- **this is an ignored error, NOT a failure**
- `Check for Full and Incr Backups in NBU`: must find both "Full Backup" and "Incr Backup"
- `Touch isBackedUp file`: marker for post-migration
- If no NBU installed: **INFO** (VM does not use NetBackup)
- If NBU present but missing backups: **WARNING**

### 3.9 CMDB / Lifecycle
- `Retrieve CloudView token`: must be `ok` (CloudGateway authentication)
- `Get status of VM in CMDB`: must be `ok`
- `Assert VM is not Decommissioning`: must be `ok` with "All assertions passed"
- If decommissioning: **BLOCKER** -- VM scheduled for removal

### 3.10 Timezone
- `Get current timezone`: info only
- `Check LocalRTC if PDT timezone`: only runs for US/Pacific, America/Los_Angeles, PST8PDT
- `Fix LocalRTC if necessary`: fixes RTC clock if needed
- If LocalRTC was wrong and fixed: **INFO** (remediated automatically)
- If timezone check skipped: no Pacific timezone, no action needed

### 3.11 Uptime
- `Verify Recent Reboot (Uptime < 30days)`: uses `ignore_errors: true`
- If uptime > 30 days: **WARNING** (stale state, boot config untested)

## Step 4: Handle Skipped Tasks Correctly

Many tasks will show as `skipping` because the playbook branches by OS version.
For example, a RHEL 8 host will skip all RHEL 7, CentOS 7, RHEL 9, Rocky, and
Ubuntu blocks. **Do not report skipped OS-specific tasks as failures.**

Count only tasks that actually executed for the host's OS path.

## Step 5: Handle Ignored Errors Correctly

Tasks with `...ignoring` in the output used `ignore_errors: true`. These are
expected scenarios, not failures:
- NetBackup binary not found (rc=127)
- Package not installed during `Protect packages from autoremove`

Report these as **INFO** or **WARNING**, not as failures.

## Step 6: Produce Verdict

Based on findings, assign:
- **READY**: No blockers, 0-2 warnings
- **READY WITH WARNINGS**: No blockers, 3+ warnings
- **NOT READY**: One or more blockers found
- **NEEDS REVIEW**: Inconclusive results (unexpected task failures)

## Step 7: When Given VMware Inventory Data (from list_vmware_vms tool)

If you receive VM properties from the MTV VMware inventory instead of Ansible
output, evaluate using these criteria:

| Check | PASS | BLOCKER | WARNING |
|-------|------|---------|---------|
| OS | RHEL 7/8/9, CentOS 7/8, Rocky 8/9, Ubuntu 20/22, Windows Server 2019/2022/2025 | Unsupported OS | -- |
| Firmware | BIOS or UEFI (OCP Virt 4.14+) | -- | UEFI: verify boot order |
| Disk | <500GB total, no RDM/shared | RDM or shared disks (unless using storage copy offload for RDM) | >4 disks (slow migration) |
| CPU/Memory | Fits within node capacity | -- | >16 vCPU or >64GB |
| Power State | Powered off (cold migration) | -- | Powered on (warm migration available) |
| Network | Single network | -- | Multiple networks (needs NetworkMap; MTV 2.11.7+ supports multi-NIC to single NAD) |

## Step 7.5: Warm Migration Readiness (MTV 2.8+ GA)

If the user requests warm migration (minimal downtime) or the VM has large disks (>500GB)
where warm migration is recommended, evaluate these additional prerequisites:

| Check | Requirement | Impact if Not Met |
|-------|-------------|-------------------|
| CBT enabled on VM | CBT must be enabled on the VM in vCenter | **BLOCKER** -- warm migration cannot track changed blocks |
| CBT enabled per disk | CBT must be enabled on EACH individual disk | **BLOCKER** -- disks without CBT will not sync incrementally |
| VDDK image configured | VDDK container image must be available in MTV config | **BLOCKER** -- required for CBT-based snapshots |
| VM not hibernated | VM must be running, not suspended/hibernated | **BLOCKER** -- hibernated VMs not supported for warm migration |
| Snapshot count | VM must have fewer than 32 existing snapshots | **BLOCKER** -- MTV warm migration is limited to 32 CBT snapshots total |
| ESXi host concurrency | Fewer than 10 warm migrations from a single ESXi host | **WARNING** -- exceeding 10 requires increasing NFC service memory on the ESXi host |
| Disk format | No independent-persistent or independent-nonpersistent disks | **BLOCKER** -- independent disks do not support CBT |

### Warm Migration Recommendation Criteria

Recommend warm migration when:
- VM has disks >500GB (cold migration downtime would be hours)
- Business requires minimal downtime (no available maintenance window)
- VM is running a stateful workload that takes time to drain

Recommend cold migration when:
- VM has disks <100GB (cold migration completes quickly)
- Maintenance window is available
- VM has complex snapshot trees (warm migration adds more snapshots)
- CBT cannot be enabled (security policy, unsupported hardware version)

## Step 8: MTV 2.11 Capability-Aware Assessment

When evaluating VMs, account for these MTV 2.11 capabilities that relax previous blockers:

### Multi-NIC to Single NAD Mapping (MTV 2.11.7+)
- VMs with multiple NICs can now map multiple source networks to a single target NAD
- Previously this required a separate NAD per source network, which was a planning blocker
- If MTV version is 2.11.7+, reduce the severity of "multiple networks" from WARNING to INFO

### Selective Shared Disk Attachment (MTV 2.11.3+)
- VMs with shared disks (e.g., MSCS clusters) can now selectively include/exclude shared disks in the migration plan
- Previously, shared disks were a hard BLOCKER
- If MTV 2.11.3+ and user confirms selective disk handling, reduce from BLOCKER to WARNING

### Windows Static IP Preservation (MTV 2.11.5, Developer Preview)
- Windows VMs can preserve static IP configuration without requiring DHCP
- Previously, Windows VMs with static IPs needed manual reconfiguration post-migration
- If MTV 2.11.5+, note this as available (Developer Preview, not for production)

### OVA Import (MTV 2.11.1+ GA)
- VMs can be imported directly from local OVA files without a VMware provider
- Useful for VMs already exported from vSphere or other hypervisors
- No vCenter connectivity required for OVA imports

## Step 9: Output

Produce a structured readiness assessment with:
1. Overall verdict (READY / READY WITH WARNINGS / NOT READY / NEEDS REVIEW)
2. VM profile summary (hostname, OS, CPU, memory, disk layout, network)
3. Per-category results table with PASS/FAIL/WARNING/SKIP/INFO
4. Blocker list with specific remediation steps
5. Warning list with recommendations
6. PLAY RECAP summary (ok/changed/failed/skipped/ignored counts)
7. Migration risk rating (LOW / MEDIUM / HIGH / CRITICAL)
8. MTV version-specific notes (capabilities that affect readiness based on the MTV version deployed)
