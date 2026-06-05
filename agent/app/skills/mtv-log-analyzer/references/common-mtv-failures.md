# Common MTV Failure Patterns

## Network Failures

### VDDK Connection Error
- **Symptoms**: `VddkError`, `Unable to connect to host`, `VDDK: error code 1`
- **Cause**: vCenter credentials incorrect, firewall blocking port 902, VDDK library version mismatch
- **Resolution**: Verify vCenter secret credentials, check network policies for port 902/443, verify VDDK version matches vCenter
- **Tags**: network, vddk, connectivity

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
- **Resolution**: Check network bandwidth ESXi-to-OCP, consider warm migration for large disks
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
