# Storage Copy Offload (MTV 2.11)

## Overview

Storage copy offload bypasses the traditional VDDK/network-based disk transfer path by copying data
directly between SAN arrays. Instead of ESXi -> network -> CDI importer -> PVC, the data moves
SAN-to-SAN (ESXi LUN -> array replication -> OCP worker LUN), dramatically reducing migration time
and network load.

GA in MTV 2.11+ for **cold migrations** only. Warm migration with XCOPY is Technology Preview in MTV 2.11
(cutover may fall back to VDDK network transfer). Not supported for live migrations.

Uses the `vmkfstools` command on ESXi hosts to invoke `XCOPY` on the storage array via iSCSI or
Fibre Channel. The source VMFS datastore and destination StorageClass must reside on the same
physical array (and same pod for Pure Storage).

## Supported Storage Arrays (MTV 2.12)

| Vendor | Product | CLI String (`storageVendorProduct`) | Notes |
|--------|---------|-------------------------------------|-------|
| Dell | PowerStore | `powerstore` | Requires VIB on ESXi hosts |
| Dell | PowerFlex | `powerflex` | Requires VIB on ESXi hosts |
| Dell | PowerMax | `powermax` | |
| Hitachi | Vantara | `vantara` | |
| NetApp | ONTAP | `ontap` | |
| HPE | Primera/3PAR | `primera3par` | |
| Pure Storage | FlashArray | `pureFlashArray` | Source and target must be on same array/pod |
| Infinidat | InfiniBox | `infinibox` | |
| IBM | FlashSystem | `flashsystem` | |

## Prerequisites

1. **VIB 0.3.0** must be installed on all ESXi hosts involved in the migration
2. SAN zoning must allow both ESXi hosts and OCP worker nodes to access the same array
3. The target OCP cluster must use a CSI driver from the same vendor (Dell CSI for PowerStore/PowerFlex)
4. MTV 2.11+ operator installed
5. StorageMap must reference the offload-capable StorageClass

## How It Works

1. MTV identifies that source VM disks reside on an offload-capable array
2. Instead of launching a VDDK transfer, MTV instructs the array to create a volume clone/snapshot
3. The cloned volume is presented to the OCP worker node via the vendor CSI driver
4. virt-v2v conversion runs on the locally-attached clone (no network transfer for disk data)

## When to Recommend

- Source VM disks are on Dell PowerStore, PowerFlex, or Infinidat InfiniBox
- Large disk migrations (>500GB) where network transfer would take hours
- Network bandwidth between VMware and OCP is limited
- Multiple large VMs need to migrate concurrently (avoids saturating the migration network)

## When NOT to Use

- Warm migration (not supported with storage copy offload)
- Source disks are on vSAN, NFS, or VMFS on non-supported arrays
- Target OCP cluster does not have the matching vendor CSI driver
- Infinidat InfiniBox in production (Developer Preview only)

## LUN Device Mapping for RDM (MTV 2.11.3+)

MTV 2.11.3 adds LUN device mapping support for Raw Device Mappings (RDM).
When source VMs use RDM LUNs on a supported array, storage copy offload can
map the RDM LUN serial to the target PVC, preserving the direct LUN relationship.

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `VIB not found` on ESXi | VIB 0.3.0 not installed | Install VIB 0.3.0 on all ESXi hosts in the migration scope |
| `populator` pod errors | SAN zoning issue; OCP worker cannot see the cloned LUN | Verify SAN zoning includes OCP worker node HBAs |
| `LUN device mapping failed` | RDM serial mismatch | Verify LUN serial numbers match between VMware RDM config and SAN array |
| Offload not triggered | StorageMap not configured for offload | Verify StorageMap references an offload-capable StorageClass; check MTV plan YAML |
| Slow despite offload | Array replication bandwidth saturated | Check array replication queue; stagger large migrations |

## Comparison: Network Transfer vs Storage Copy Offload

| Aspect | Network Transfer (VDDK) | Storage Copy Offload |
|--------|------------------------|---------------------|
| Data path | ESXi -> network -> CDI importer -> PVC | ESXi LUN -> SAN clone -> OCP worker LUN |
| Speed | Limited by network bandwidth | Limited by SAN replication speed (typically faster) |
| Network impact | High (all disk data traverses the migration network) | Minimal (only metadata over network) |
| Supported migration types | Cold, warm | Cold only |
| VDDK required | Yes | No (but VIB 0.3.0 required on ESXi) |
| Array requirement | None | Dell PowerStore/PowerFlex or Infinidat InfiniBox |
