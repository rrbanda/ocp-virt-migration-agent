# Pre-Migration Playbook Task Map

Maps each task name from the customer's pre-migration playbook to its check
category. Use this to produce structured assessment reports from parsed output.

Play name: `Pre-migration Check`

## Hypervisor Checks

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Identify current hypervisor | Hypervisor | `changed` (dmidecode ran) |
| Assert VM is on VMware | Hypervisor | `ok` with "All assertions passed" |

## OS Validation

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Operating System | OS | `ok` (debug -- shows distro + version, e.g., "RedHat 8.10") |
| Verify Valid OS | OS | `ok` -- confirms supported distro |

## NFS / Remote Filesystem

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Detect active nfs mount | Network/Storage | `ok` (rc=0 means NFS present, rc=1 no NFS) |
| Check if system has NFS mount (is-enabled) | Network/Storage | `ok` or `skipping` (conditional on NFS detection) |
| Assert remote-fs is enabled if there are NFS mounts | Network/Storage | `ok` -- only runs when NFS detected |

## VMware Tools

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Check if vmware-guest-tools installed | Packages | `changed` (rc=0 means tools found -- vmware-toolbox-cmd -v) |
| Check if vmtoolsd.service is running | Packages | `changed` (rc=0 means running) |

## Kernel / Boot (RHEL/CentOS 7)

These tasks run ONLY for RHEL 7 or CentOS 7. All will be `skipping` for other OSes.

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Read in /proc/cmdline | Kernel | `ok` |
| List kernelopts from proccmdline in Red Hat | Kernel | `ok` (produces list) |
| Read in grub2-mkconfig and get output Red Hat 7 | Kernel | `changed` (uses grubby) |
| Ensure that when v2v generates new grub the kernel args match Red Hat | Kernel | `ok` -- proccmdline_list and grubgen_list must have zero differences |
| Preserve a copy of /etc/default/grub | Kernel | `changed` (backup) |
| Preserve a copy of /etc/grub2.cfg Redhat | Kernel | `changed` (backup) |
| List kernel packages Red Hat | Kernel | `changed` (rpm -qa kernel) |
| Assert running kernel is installed package | Kernel | `ok` |
| Stat grubenv | Kernel | `ok` |
| grubenv is exactly 1024 bytes | Kernel | `ok` |

## Kernel / Boot (RHEL/Rocky 8/9)

These tasks run ONLY for RHEL 8/9 or Rocky 8/9. All will be `skipping` for other OSes.

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Read in /proc/cmdline | Kernel | `ok` |
| List kernelopts from proccmdline in Red Hat or Rocky | Kernel | `ok` (produces list) |
| Read in grub2-mkconfig and get output Red Hat or Rocky 8 or 9 | Kernel | `changed` (grub2-mkconfig --no-grubenv-update) |
| Stat /var/opt/defaultgrub.bak | Kernel | `ok` |
| Preserve a copy of /etc/default/grub | Kernel | `changed` (backup) |
| Copy sync-default-grub.sh | Kernel | `changed` (only if params diverge) |
| Run sync-default-grub.sh | Kernel | `changed` (only if params diverge) |
| Read in again grub2-mkconfig | Kernel | `changed` (re-read after sync) |
| Ensure that when v2v generates new grub the kernel args match Red Hat or Rocky | Kernel | `ok` -- proccmdline_list and grubgen_list must have zero differences |
| Preserve a copy of /etc/grub2.cfg Redhat or Rocky | Kernel | `changed` (backup) |
| List kernel packages Red Hat or Rocky | Kernel | `changed` (rpm -qa kernel) |
| Assert running kernel is installed package | Kernel | `ok` |
| Stat grubenv | Kernel | `ok` |
| grubenv is exactly 1024 bytes | Kernel | `ok` |
| Check partitions for bootflag | Kernel | `changed` with stdout "1" (RHEL8+ only) |

## Kernel / Boot (Ubuntu)

These tasks run ONLY for Ubuntu. All will be `skipping` for other OSes.

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Read in grub env Ubuntu | Kernel | `ok` |
| Preserve a copy of /boot/grub/grub.cfg Ubuntu | Kernel | `changed` |
| Stat grubenv | Kernel | `ok` |
| grubenv is exactly 1024 bytes | Kernel | `ok` |

## RPM Database

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Check if rpmdb_fix.sh already exists | Packages | `ok` (stat check) |
| Copy rpmdb_fix.sh to VM and make it executable | Packages | `changed` (if not already exists) |
| Execute rpmdb_fix.sh | Packages | `changed` -- inspect stdout for key indicators |
| Display rmpdb_result | Packages | `ok` -- stdout shows: uptime, hung process count, var filesystem usage, corruption check, rebuild status, package count |

### rpmdb_fix.sh Output Interpretation

Look for these lines in the `Display rmpdb_result` stdout:
- `"Host {hostname} uptime is {N}d {N}h {N}m {N}s."` -- uptime info
- `"var filesystem is good. Current usage {N}%."` -- var usage OK
- `"Total hung rpm processes are: 0"` -- no hung RPM processes
- `"Total hung yum processes are: 0"` -- no hung yum processes
- `"Total hung subscription manager processes are: 0"` -- no hung sub-mgr processes
- `"No hung process found."` -- all clear
- `"RPMDB not corrupted"` -- database is clean
- `"RPMDB Rebuild successful"` -- rebuild completed
- `"rpm -qa command generated output. Total {N} packages."` -- package count

If "RPMDB corrupted" appears, this is a **WARNING**.

## Disk / Filesystem

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Verify fstab does not contain /dev/sd | Disk | `ok` (no /dev/sd entries found) |
| Check partitions for bootflag | Disk | `changed` with stdout "1" (RHEL8+ only) |
| Check partitions for crypt | Disk | `changed` with stdout "0" (no encrypted partitions) |
| Augtool check fstab for errors | Disk | `changed` with stdout "0" (no fstab parse errors) |
| Check if check-filesystem-usage.ksh already exists | Disk | `ok` (stat check) |
| Copy check-filesystem-usage.ksh to VM | Disk | `changed` (if not exists) |
| Execute check-filesystem-usage.ksh | Disk | `changed` -- inspect stdout for usage info |
| Display filesystem_usage_results | Disk | `ok` -- shows largest files/dirs and recommendations |
| Mount points | Disk | `ok` -- debug output showing all mounts with sizes |
| Root mount point freespace > 100MB | Disk | `ok` per mount item where mount == "/" |
| Boot mount point freespace > 50MB | Disk | `ok` per mount item where mount == "/boot" |
| Other mount point freespace > 10MB | Disk | `ok` per mount item (excludes /, /boot, loop, sys, run, nfs, cifs, fuse, autofs) |

## Package Installability (OS-Specific)

Only one of these blocks will run based on the host's OS. Others will be `skipping`.

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Check if qemu-guest-agent can be installed by MTV | Packages | `changed`/`ok` (download succeeded from OS-specific repos) |
| Ensure selinux-policy-targeted installed | Packages | `ok`/`changed` |
| Protect packages from autoremove of open-vm-tools | Packages | `changed` per item -- some fail for uninstalled packages (`ignore_errors`) |
| Ensure augeas tool installed | Packages | `ok`/`changed` (RHEL8/9, Rocky8/9 only -- for fstab check) |
| Ensure augeas tool uninstalled | Packages | `ok`/`changed` (cleanup after fstab check) |

## Timezone

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Get current timezone | System | `ok`/`changed` (info -- shows current TZ) |
| Check LocalRTC if PDT timezone | System | `ok`/`skipping` (only for US/Pacific, America/Los_Angeles, PST8PDT) |
| Fix LocalRTC if necessary | System | `changed` or `skipping` |

## Uptime

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Verify Recent Reboot (Uptime < 30days) | System | `ok` with "All assertions passed" -- uses `ignore_errors: true` |

## Backup

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Run Netbackup tool | Backup | `changed` (rc=0 means NBU present); `fatal` with rc=127 means no NBU -- `ignore_errors` |
| Check for Full and Incr Backups in NBU | Backup | `ok` if both "Full Backup" and "Incr Backup" found (only runs when NBU present) |
| Touch isBackedUp file | Backup | `changed` if backups confirmed |

## CMDB / Lifecycle

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Get osvmigration service account | CMDB | `ok` (loads env vars -- no_log) |
| Retrieve CloudView token | CMDB | `ok` (CloudGateway POST succeeded) |
| Check CloudGateway token response | CMDB | `ok` (authToken present) |
| Extract CloudView token from response | CMDB | `ok` |
| Get status of VM in CMDB | CMDB | `ok` (GET succeeded) |
| Assert VM is not Decommissioning | CMDB | `ok` with "All assertions passed" |

## Working Directory / Facts Persistence

| Task Name | Category | Pass Criteria |
|-----------|----------|---------------|
| Get osvmig_ dirs from var opt | System | `ok` |
| Delete osvmig_ dirs | System | `changed` per item (cleanup old runs) |
| Create migration working directory | System | `changed` (creates /var/opt/osvmig_{random}) |
| Write AnsibleFacts to file | System | `changed` (saves ansiblefacts.json) |
| CPU and Memory | System | `ok` (debug -- extract vCPU and memory_mb values) |
| Network Interfaces | System | `ok` (debug -- extract interface names, MACs, and IPs) |
| Mount points | System | `ok` (debug -- all mount points with sizes) |
| Change Owner | System | `changed` (sets ownership to svcansible:ansible) |
