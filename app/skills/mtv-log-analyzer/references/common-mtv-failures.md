# Common MTV Failure Patterns

Reference for MTV 2.8 – 2.11. Covers cold, warm, and live migration failure modes.

## MTV 2.11 Diagnostic Workflow

When a migration fails, follow this structured diagnostic sequence:

1. **Check plan status and conditions:**
   ```bash
   oc get plan <plan-name> -n <mtv-ns> -o yaml
   # Look at status.conditions for error messages
   ```
2. **Examine pod logs (forklift-controller, virt-v2v):**
   ```bash
   oc logs -n openshift-mtv deploy/forklift-controller --tail=200
   oc logs -n <mtv-ns> <virt-v2v-pod> --tail=200
   ```
3. **Review inventory service:**
   ```bash
   oc logs -n openshift-mtv deploy/forklift-inventory --tail=100
   ```
4. **Collect must-gather:**
   ```bash
   oc adm must-gather --image=registry.redhat.io/migration-toolkit-virtualization/mtv-must-gather-rhel8
   ```

## Network Failures

### VDDK Connection Error
- **Symptoms**: `VddkError`, `Unable to connect to host`, `VDDK: error code 1`
- **Cause**: vCenter credentials incorrect, firewall blocking port 902, VDDK library version mismatch
- **Resolution**: Verify vCenter secret credentials, check network policies for port 902/443, verify VDDK version matches vCenter
- **Tags**: network, vddk, connectivity

### VDDK Required on vSAN
- **Symptoms**: Migration fails immediately when source datastore is vSAN, error referencing VDDK
- **Cause**: MTV cannot migrate from vSAN datastores without VDDK; network-based transfer (nbdkit) is not supported for vSAN
- **Resolution**: Ensure VDDK container image is configured in MTV. There is no workaround for vSAN without VDDK.
- **Tags**: network, vddk, vsan, mtv-2.11

### SSL Certificate Error
- **Symptoms**: `certificate verify failed`, `x509`, `TLS handshake error`
- **Cause**: vCenter using self-signed cert not in MTV trust store
- **Resolution**: Add CA cert to forklift-controller ConfigMap `forklift-controller-config`
- **Tags**: network, ssl, certificates

### ESXi Host Unreachable
- **Symptoms**: `Unable to connect to ESXi host`, `connection refused on port 902`
- **Cause**: ESXi host firewall rules, maintenance mode, or network isolation
- **Resolution**: Check ESXi host firewall for port 902, verify host is not in maintenance mode
- **Tags**: network, esxi, connectivity

## Storage Failures

### PVC Not Bound
- **Symptoms**: DataVolume stuck in `WaitForFirstConsumer` or `Pending`
- **Cause**: No StorageClass matching request, insufficient capacity, quota exceeded
- **Resolution**: Check StorageClass exists, verify PV capacity, check ResourceQuota
- **Tags**: storage, pvc, provisioning

### Disk Transfer Timeout
- **Symptoms**: Migration stuck at <100% progress for >2 hours, no progress change
- **Cause**: Slow network between ESXi and OCP, large disk (>500GB), VDDK throttling
- **Resolution**: Check network bandwidth ESXi-to-OCP, consider warm migration for large disks, or storage copy offload if Dell/Infinidat SAN is available
- **Tags**: storage, performance, timeout

### CDI Importer Failure
- **Symptoms**: `cdi-importer` pod in CrashLoopBackOff, `Unable to process data`
- **Cause**: Corrupted VMDK, unsupported disk format (thick provisioned + snapshots)
- **Resolution**: Consolidate snapshots before migration, verify disk format compatibility
- **Tags**: storage, cdi, disk-format

### Insufficient Disk Space
- **Symptoms**: `No space left on device`, PVC bound but import fails
- **Cause**: Target PVC size smaller than source disk, storage class thin-provision overhead
- **Resolution**: Increase PVC size, check storage class provisioner capacity
- **Tags**: storage, capacity, pvc

### Storage Copy Offload Failure (MTV 2.11)
- **Symptoms**: Migration plan with storage copy offload enabled fails, `populator` pod errors, `VIB not found` on ESXi
- **Cause**: VIB 0.3.0 not installed on ESXi hosts, SAN zoning misconfigured, or unsupported array firmware
- **Resolution**: Verify VIB 0.3.0 is installed on all ESXi hosts involved, check SAN zoning between ESXi and OCP worker nodes, verify array firmware compatibility (Dell PowerStore/PowerFlex GA, Infinidat InfiniBox Developer Preview)
- **Tags**: storage, offload, san, mtv-2.11

### Storage Copy Offload LUN Mapping Error (MTV 2.11)
- **Symptoms**: `LUN device mapping failed`, storage copy offload cannot locate source LUN
- **Cause**: RDM LUN device mapping not configured, or LUN serial mismatch between ESXi and array
- **Resolution**: Verify LUN serial numbers match between VMware RDM and SAN array. Use MTV 2.11.3+ which adds LUN device mapping support for RDM in storage copy offload.
- **Tags**: storage, offload, rdm, lun, mtv-2.11

## Warm Migration Failures (MTV 2.8+ GA)

### Warm Import Retry Limit Reached
- **Symptoms**: `Warm import retry limit reached`, migration stuck after many incremental cycles
- **Cause**: VM exceeded the 32 CBT snapshot limit. MTV creates a snapshot every hour by default; after 32 snapshots the warm migration fails.
- **Resolution**: Cancel the migration, consolidate all snapshots on the VM in vCenter, then restart the warm migration. For VMs that need >32 hours of incremental sync, increase the `SNAPSHOT_INTERVAL` in forklift-controller to reduce snapshot frequency.
- **Tags**: warm, cbt, snapshot-limit, mtv-2.8

### CBT Not Enabled
- **Symptoms**: Warm migration starts but transfers full disk instead of incremental, or fails with CBT-related error
- **Cause**: CBT (Changed Block Tracking) not enabled on the VM or on individual disks in vCenter
- **Resolution**: Enable CBT on the VM AND on each individual disk via vCenter. Power-cycle the VM after enabling CBT for it to take effect.
- **Tags**: warm, cbt, configuration, mtv-2.8

### Hibernated VM Warm Migration
- **Symptoms**: Warm migration fails immediately for suspended/hibernated VM
- **Cause**: Hibernated VMs are not supported for warm migration; the suspend state conflicts with CBT snapshot creation
- **Resolution**: Resume the VM from hibernation before starting warm migration, or use cold migration instead.
- **Tags**: warm, hibernated, unsupported, mtv-2.8

### ESXi NFC Memory Exhaustion
- **Symptoms**: Warm migrations from the same ESXi host start failing after ~10 concurrent VMs, NFC connection errors
- **Cause**: Each warm migration maintains an NFC (Network File Copy) session on the ESXi host. Default NFC service memory is insufficient for >10 concurrent sessions.
- **Resolution**: Increase NFC service memory on the ESXi host, or limit concurrent warm migrations to ≤10 per ESXi host.
- **Tags**: warm, esxi, nfc, concurrency, mtv-2.8

### Cutover Scheduling Failure
- **Symptoms**: Scheduled cutover time passes but cutover does not execute
- **Cause**: `cutover` timestamp in the Migration manifest is in the past or uses wrong timezone format
- **Resolution**: Verify the cutover timestamp uses RFC 3339 format (e.g., `2025-03-15T02:00:00Z`) and is in the future. Check forklift-controller logs for scheduling errors.
- **Tags**: warm, cutover, scheduling, mtv-2.8

## Conversion Failures

### virt-v2v Error
- **Symptoms**: virt-v2v pod fails, `inspection` errors, `No operating system found`
- **Cause**: Unsupported guest OS, corrupted disk, missing drivers, GPT vs MBR mismatch
- **Resolution**: Check OS compatibility matrix, run pre-migration assessment playbook
- **Tags**: conversion, virt-v2v, compatibility

### Boot Failure Post-Conversion
- **Symptoms**: VM created but won't boot, grub errors, kernel panic
- **Cause**: Kernel/grub mismatch, missing boot flag, grubenv corruption (not 1024 bytes)
- **Resolution**: Run pre-migration assessment to catch these before migration; fix grub2-mkconfig, verify grubenv size
- **Support KB**: Pre-migration playbook tasks "grubenv is exactly 1024 bytes" and "kernel args match" catch this
- **Tags**: conversion, boot, kernel

### UEFI Boot Failure
- **Symptoms**: VM boots to EFI shell, `No bootable device`
- **Cause**: UEFI firmware not properly converted, secure boot incompatibility
- **Resolution**: Check firmware setting in VM spec, disable secure boot if needed
- **Tags**: conversion, uefi, firmware

### fstab Errors Post-Conversion
- **Symptoms**: VM boots but mounts fail, read-only filesystem
- **Cause**: /dev/sd references in fstab not converted to /dev/vd, fstab parse errors
- **Resolution**: Pre-migration playbook checks "Verify fstab does not contain /dev/sd" and "Augtool check fstab for errors"
- **Tags**: conversion, fstab, disk

## Resource Failures

### OOM Kill
- **Symptoms**: Pod evicted, `OOMKilled` status on virt-v2v or cdi-importer pod
- **Cause**: Conversion process exceeded memory limits (common with >200GB disks)
- **Resolution**: Increase resource limits on forklift-controller deployment, or process fewer VMs in parallel
- **Tags**: resources, memory, oom

### CPU Throttling
- **Symptoms**: Migration extremely slow, virt-v2v pod CPU usage at limit
- **Cause**: Resource limits too low for conversion workload
- **Resolution**: Increase CPU limits, reduce concurrent migrations
- **Tags**: resources, cpu, throttling

## Pre-Migration Blockers (from AAP Playbook)

### Encrypted Partitions
- **Symptoms**: Pre-migration playbook "Check partitions for crypt" fails
- **Cause**: VM has LUKS-encrypted partitions; virt-v2v cannot convert these
- **Resolution**: Decrypt partitions before migration or exclude VM
- **Tags**: pre-migration, encryption, blocker

### Missing Boot Flag
- **Symptoms**: Pre-migration playbook "Check partitions for bootflag" fails (count != 1)
- **Cause**: No boot flag on any partition, or multiple boot flags
- **Resolution**: Use `fdisk` to set exactly one boot flag on the correct partition
- **Tags**: pre-migration, boot, fdisk

### RPM Database Corruption
- **Symptoms**: Pre-migration playbook rpmdb_fix.sh reports "RPMDB corrupted"
- **Cause**: Interrupted yum/dnf transaction, filesystem corruption
- **Resolution**: Run `rpm --rebuilddb`, verify package count looks reasonable
- **Tags**: pre-migration, rpmdb, packages
