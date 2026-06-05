# Pre-Migration Checklist Reference

Derived from the customer's actual 1100-line pre-migration Ansible playbook.
Each check maps directly to a named task in the playbook output.

## Blocker Checks (Must Pass or Migration Cannot Proceed)

| # | Category | Ansible Task Name | Pass Criteria | Failure Impact |
|---|----------|-------------------|---------------|----------------|
| 1 | Hypervisor | `Identify current hypervisor` | `changed` (dmidecode ran successfully) | Cannot identify platform |
| 2 | Hypervisor | `Assert VM is on VMware` | `ok` with "All assertions passed" | Cannot migrate non-VMware VMs |
| 3 | OS | `Operating System` | `ok` (debug -- shows distro + version) | Info only |
| 4 | OS | `Verify Valid OS` | `ok` with "All assertions passed" | Unsupported OS blocks migration |
| 5 | Kernel | `Read in /proc/cmdline` | `ok` (slurp succeeded) | Cannot verify boot config |
| 6 | Kernel | `List kernelopts from proccmdline` | `ok` (fact set) | Cannot compare kernel params |
| 7 | Kernel | `Read in grub2-mkconfig and get output` | `changed` (grub config read) | Cannot verify grub consistency |
| 8 | Kernel | `Ensure that when v2v generates new grub the kernel args match` | `ok` with "All assertions passed" -- proccmdline_list must equal grubgen_list with zero differences | VM will not boot after migration if grub params diverge |
| 9 | Kernel | `Preserve a copy of /etc/default/grub` | `changed` (backup created) | No rollback possible |
| 10 | Kernel | `Preserve a copy of /etc/grub2.cfg` | `changed` (backup created) | No rollback possible |
| 11 | Kernel | `List kernel packages` | `changed` (rpm -qa kernel ran) | Cannot verify kernel match |
| 12 | Kernel | `Assert running kernel is installed package` | `ok` with "All assertions passed" | Kernel mismatch causes boot failure |
| 13 | Kernel | `Stat grubenv` | `ok` (file stat returned) | Cannot verify grubenv |
| 14 | Kernel | `grubenv is exactly 1024 bytes` | `ok` with "All assertions passed" | Corrupted grub, boot failure |
| 15 | Disk | `Verify fstab does not contain /dev/sd` | `ok` (no changes found) | Disk paths change after migration, VM won't mount filesystems |
| 16 | Disk | `Check partitions for bootflag` | `changed` with stdout "1" (exactly one boot partition) | VM may not boot (RHEL8+ only) |
| 17 | Disk | `Check partitions for crypt` | `changed` with stdout "0" (no encrypted partitions) | Encryption not supported by MTV |
| 18 | Disk | `Augtool check fstab for errors` | `changed` with stdout "0" (no fstab parse errors) | Mount failures after migration |
| 19 | Packages | `Check if qemu-guest-agent can be installed by MTV` | `changed`/`ok` (download succeeded) | Guest agent required for OCP Virt |
| 20 | CMDB | `Assert VM is not Decommissioning` | `ok` with "All assertions passed" | VM scheduled for removal |

## Warning Checks (Non-Blocking but Should Be Addressed)

| # | Category | Ansible Task Name | Pass Criteria | Impact |
|---|----------|-------------------|---------------|--------|
| 21 | Disk | `Root mount point freespace > 100MB` | `ok` per mount item where mount == "/" | May fail during migration if root is full |
| 22 | Disk | `Boot mount point freespace > 50MB` | `ok` per mount item where mount == "/boot" | May fail during migration if boot is full |
| 23 | Disk | `Other mount point freespace > 10MB` | `ok` per mount item (excludes /, /boot, loop, sys, run, nfs, cifs, fuse, autofs) | Applications may fail post-migration |
| 24 | RPM DB | `Execute rpmdb_fix.sh` | `changed` -- look at stdout for "RPMDB not corrupted" and package count | Corrupted RPM DB causes package management issues |
| 25 | Network | `Detect active nfs mount` | `ok` (rc=0 means NFS present, rc=1 means no NFS) | Determines if remote-fs check is needed |
| 26 | Network | `Check if system has NFS mount (is-enabled)` | `ok` or `skipping` (skipped when no NFS) | Conditional on NFS detection |
| 27 | Network | `Assert remote-fs is enabled if there are NFS mounts` | `ok` (only runs when NFS detected) | NFS mounts fail after reboot without remote-fs.target |
| 28 | Backup | `Run Netbackup tool` | `changed` (rc=0 means NBU present); `fatal` with rc=127 means no NBU -- uses `ignore_errors` | No rollback available |
| 29 | Backup | `Check for Full and Incr Backups in NBU` | `ok` if both "Full Backup" and "Incr Backup" in output (only runs when NBU present) | No verified backup before migration |
| 30 | Backup | `Touch isBackedUp file` | `changed` if backups confirmed (creates marker file) | Backup status marker for post-migration |
| 31 | Uptime | `Verify Recent Reboot (Uptime < 30days)` | `ok` with "All assertions passed" -- uses `ignore_errors: true` | Stale state, untested boot config |
| 32 | Packages | `Ensure selinux-policy-targeted installed` | `ok`/`changed` | SELinux policy needed for OCP Virt |
| 33 | Packages | `Protect packages from autoremove of open-vm-tools` | `changed` per item -- some may fail for uninstalled packages (uses `ignore_errors`) | Prevents accidental removal of dependencies during migration |
| 34 | Timezone | `Get current timezone` | `ok`/`changed` (info only) | Determines if LocalRTC fix is needed |
| 35 | Timezone | `Check LocalRTC if PDT timezone` | `ok`/`skipping` (only runs for US/Pacific, America/Los_Angeles, PST8PDT) | Time sync issues after migration |
| 36 | Timezone | `Fix LocalRTC if necessary` | `changed` or `skipping` | Fixes RTC clock for Pacific timezone VMs |

## OS-Specific Repo Configuration

The playbook uses different repos for qemu-guest-agent installation per OS:

| OS | Repos Used |
|----|-----------|
| RHEL 7 | `rhel-7-server-rpms`, `rhel-7-server-optional-rpms`, `rhel-server-rhscl-7-rpms` |
| CentOS 7 | `xyz_centos7-x86_64_centos7-x86_64_os`, `xyz_centos7-x86_64_centos7-x86_64_updates`, `xyz_centos7-x86_64_centos7-x86_64_extras`, `xyz_centos7-x86_64_hashed-ciq_cbr_79-x86_64_updates` |
| RHEL 8 | `rhel-8-for-x86_64-baseos-rpms`, `rhel-8-for-x86_64-appstream-rpms` |
| RHEL 9 | `rhel-9-for-x86_64-baseos-rpms`, `rhel-9-for-x86_64-appstream-rpms` |
| Rocky 8 | `xyz_rocky8-x86_64_rocky8-x86_64_baseos`, `xyz_rocky8-x86_64_rocky8-x86_64_appstream`, `xyz_rocky8-x86_64_rocky8-x86_64_extras` |
| Rocky 9 | `xyz_rocky_rocky9-x86_64_baseos`, `xyz_rocky_rocky9-x86_64_appstream` |
| Ubuntu 20/22 | Default apt repos (`apt download qemu-guest-agent`) |

## Kernel Handling Branches

The playbook has three kernel-handling branches based on OS:

1. **RHEL/CentOS 7**: Uses `grubby` to read kernel opts, compares `/proc/cmdline` vs grubby output
2. **RHEL/Rocky 8/9**: Uses `grub2-mkconfig --no-grubenv-update`, also includes boot flag check and `sync-default-grub.sh` remediation if params diverge
3. **Ubuntu**: Reads `/boot/grub/grubenv`, checks grubenv size (1024 bytes)

## Protected Packages (Prevent Autoremove)

These packages are marked as user-installed to prevent autoremove when open-vm-tools is removed:
`xmlsec1-openssl`, `xmlsec1`, `fuse`, `fuse-common`, `fuse-libs`, `libxslt`, `libmspack`, `libffi`, `libffi-devel`, `pciutils`

## CMDB Integration

1. Retrieve CloudGateway token from `cloudgateway.trusted.xyz.com:8443`
2. Query VM lifecycle status via `/cloudgateway/asknow/ci-servers/host-name/{hostname}`
3. Assert lifecycle status is NOT "Decommissioning"

## Facts Persistence

The playbook saves Ansible facts to `ansiblefacts.json` in the working directory for post-migration comparison:
- CPU: `ansible_facts.processor_vcpus`
- Memory: `ansible_facts.memtotal_mb`
- Network: `ansible_facts.interfaces` with IP/MAC per interface
- Mounts: `ansible_facts.mounts` with sizes and free space
- Kernel: `ansible_facts.kernel`
- OS: `ansible_facts.distribution` + `distribution_version`

## Ownership

Final task changes working directory ownership to `svcansible:ansible`.

## Interpreting the Output

### Skipped Tasks
Many tasks will show as `skipping` because the playbook has OS-specific blocks. For a RHEL 8 host, all RHEL 7, CentOS 7, RHEL 9, Rocky 8/9, and Ubuntu blocks will be skipped. This is normal -- only count tasks that actually ran.

### Ignored Errors
Two common ignored errors:
1. **NetBackup not found** (`fatal` with rc=127): Normal for VMs without NetBackup. The `ignore_errors` flag means this is not a failure.
2. **Package not installed** during `Protect packages from autoremove`: Some packages (e.g., `libffi-devel`) may not be installed. The error is ignored.

### PLAY RECAP
The summary line shows totals: `ok=N changed=N unreachable=N failed=N skipped=N rescued=N ignored=N`
- `failed=0` means the playbook completed successfully
- `ignored` count reflects tasks that failed but had `ignore_errors: true`
- High `skipped` count is normal due to OS-specific branching
