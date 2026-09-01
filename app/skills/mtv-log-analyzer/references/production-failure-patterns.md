# Production-Scale Failure Patterns

## Connection Pool Exhaustion

- **Symptoms**: Multiple simultaneous migrations slow down, VDDK errors, timeouts
- **Cause**: Too many concurrent disk transfers saturating VDDK connections to vCenter
- **Resolution**: Limit concurrent migrations to 3-5 per wave. Increase forklift-controller resource limits.
- **Prevention**: Never run more than 5 concurrent migrations per ESXi host

## Storage Network Saturation

- **Symptoms**: Disk transfer at 10-20% progress for hours, ODF performance degradation
- **Cause**: Multiple large disk transfers (>500GB each) saturating the storage network
- **Resolution**: Stagger large VM migrations. Use dedicated storage network (Multus for ODF).
- **Prevention**: Schedule large VMs in separate waves. Use warm migration for disks >500GB.

## NIC Filter False Positive

- **Symptoms**: MTV shows warning "NIC filter not supported" on all VMs
- **Cause**: VMware VMs have MAC spoof filtering enabled by default. MTV warns about this.
- **Reality**: If the target NAD has `macspoofchk: true`, this is a false positive.
- **Resolution**: Safe to ignore if target NAD has spoof checking enabled. Proceed with migration.

## VDDK Image Not Found

- **Symptoms**: Migration fails immediately, "VDDK not configured" error
- **Cause**: VDDK image not uploaded to internal registry or image reference incorrect
- **Resolution**: Download VDDK from VMware, build container image, push to internal registry, update MTV config

## Migration Type Selection

MTV 2.8+ supports three GA migration types for production use:

- **Cold migration** (GA): VM powered off, full disk copy. Most reliable, causes full downtime.
- **Warm migration** (GA since MTV 2.8): CBT-based incremental copy while VM runs, minutes of downtime at cutover. Production-ready for VMware and RHV sources.
- **Live migration** (GA since MTV 2.10): Zero-downtime between OCP Virt clusters. Requires OCP Virt 4.20+ on both clusters.

**Recommendation**: Use warm migration for large VMs (>500GB disks) or when downtime must be minimized. Use cold migration for smaller VMs or when a maintenance window is available. Use live migration for cross-cluster OCP Virt moves.

## CSI Driver Quirks

### HPE
- FC-only arrays: `group --edit --iscsi_enabled yes` needed for RWX block workaround
- NFS Server Provisioner required for RWX

### Dell
- NVMe mounts on PowerStore fail in CSI v2.11; use v2.10.1
- PowerFlex: NFS connectivity only

### Portworx
- PX CSI does NOT support KubeVirt -- do not use for OCP Virt VMs
- RWX block coming Q1/25

### NetApp
- Trident v24.06+ needed for full OCP 4.16 support
- FC support coming Q1 2025

## Warm Migration Production Failures

### CBT Snapshot Accumulation
- **Symptoms**: Warm migration runs for >32 hours, then fails with `Warm import retry limit reached`
- **Cause**: MTV creates a CBT snapshot every hour by default. After 32 snapshots, the limit is hit.
- **Prevention**: For VMs with very high change rates, increase `SNAPSHOT_INTERVAL` in forklift-controller to reduce frequency. Plan cutover within 24 hours of starting warm migration.
- **Resolution**: Cancel migration, consolidate all snapshots in vCenter, restart warm migration with larger interval or schedule cutover sooner.

### Warm Migration Stall on High-Change-Rate VMs
- **Symptoms**: Incremental copy cycles never converge (each cycle transfers nearly as much as the first)
- **Cause**: VM has extremely high disk write rate (e.g., database under heavy load). Each incremental cycle finds nearly all blocks changed.
- **Prevention**: Reduce VM write load before cutover (quiesce applications, stop batch jobs).
- **Resolution**: Schedule cutover during off-peak hours when write rate is lowest. Accept that final cutover will still require copying recent changes.

### ESXi Host NFC Overload
- **Symptoms**: Warm migrations from the same ESXi host fail after ~10 concurrent VMs
- **Cause**: Each warm migration maintains an NFC session; default ESXi NFC service memory is limited
- **Prevention**: Limit concurrent warm migrations to ≤10 per ESXi host. Stagger migration waves by ESXi host.
- **Resolution**: Increase NFC service memory on the ESXi host or reduce concurrent warm migration count.

### Cutover Window Missed
- **Symptoms**: Scheduled cutover time passed but source VM is still running, migration shows no cutover activity
- **Cause**: Cutover timestamp format error, forklift-controller pod restarted between scheduling and cutover time
- **Prevention**: Use manual cutover for critical VMs. Verify scheduled cutover with `oc get migration -o yaml`.
- **Resolution**: Trigger manual cutover or update the timestamp. Check forklift-controller pod uptime.

## Storage Copy Offload Production Failures (MTV 2.11)

### VIB Not Installed
- **Symptoms**: Storage copy offload plan fails immediately, ESXi host logs show VIB-related errors
- **Cause**: VIB 0.3.0 not installed on all ESXi hosts in scope
- **Prevention**: Pre-install VIB 0.3.0 on all ESXi hosts before creating offload migration plans
- **Resolution**: Install VIB, verify with `esxcli software vib list | grep forklift`, retry migration

### SAN Zoning Mismatch
- **Symptoms**: Populator pod cannot attach cloned LUN, `volume not found` errors
- **Cause**: OCP worker nodes not zoned to see the cloned LUNs on the SAN
- **Prevention**: Verify SAN zoning includes both ESXi host HBAs and OCP worker node HBAs
- **Resolution**: Update SAN zoning to include OCP worker HBAs, rescan storage on workers

### Array Replication Queue Saturation
- **Symptoms**: Multiple storage copy offload migrations queued, individual migrations very slow
- **Cause**: SAN array replication bandwidth saturated by too many concurrent clone operations
- **Prevention**: Limit concurrent storage copy offload migrations based on array capacity
- **Resolution**: Stagger migrations, check array replication queue depth

## Escalation Procedures

When to open a Red Hat support case:
1. Migration fails with no clear error in forklift-controller logs
2. virt-v2v conversion error (OS not detected, boot failure)
3. CDI importer crash loops
4. Cluster instability during migration
5. Warm migration CBT errors not resolved by snapshot consolidation
6. Storage copy offload failures after verifying VIB and zoning

Data to collect:
```bash
# MTV logs
oc logs -n openshift-mtv deploy/forklift-controller > forklift.log

# Must-gather (MTV 2.11)
oc adm must-gather --image=registry.redhat.io/migration-toolkit-virtualization/mtv-must-gather-rhel8

# Specific VM migration logs
oc get migration <name> -n <ns> -o yaml > migration.yaml

# Plan status and conditions
oc get plan <name> -n <ns> -o yaml > plan.yaml
```
