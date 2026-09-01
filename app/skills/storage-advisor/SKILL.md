---
name: storage-advisor
description: >-
  Advises on storage architecture for OpenShift Virtualization. Covers ODF
  deployment models (internal/external/HCI), CSI driver comparison for
  major vendors (HPE, Dell, NetApp, IBM, Portworx), RWO vs RWX requirements,
  disaster recovery options, and storage decision guidance.
---

# Storage Architecture Advisor

Help the user choose and configure the right storage for their OCP Virt deployment.

## Step 1: Understand Requirements

Ask about:
- Current VMware storage (VMFS, vSAN, NFS, FC SAN?)
- Existing storage hardware (vendor, model)
- Live migration requirement (needs RWX)
- Disaster recovery requirements (metro DR, regional DR?)
- Total VM disk capacity needed

## Step 2: Recommend Storage Approach

Read `references/decision-tree.md` for the decision framework.

Quick guide:
- **No existing SAN**: Use ODF internal (HCI) mode
- **Existing SAN (HPE/Dell/NetApp/IBM)**: Use vendor CSI driver
- **Need both**: Mixed mode (CSI for block, ODF for file/object)
- **Large scale (100+ VMs)**: Consider ODF external mode with dedicated Ceph

### Storage Copy Offload (MTV 2.11)

If the customer has Dell PowerStore, Dell PowerFlex, or Infinidat InfiniBox arrays,
recommend **storage copy offload** for cold migrations. This bypasses network-based
disk transfer entirely by cloning data at the SAN level -- dramatically faster for
large disks and eliminates migration network saturation.

Read `references/storage-copy-offload.md` for prerequisites, supported arrays, and troubleshooting.

## Step 3: Validate RWX Support

Live migration requires RWX (ReadWriteMany) storage:

| Storage | RWX Block | RWX File | Live Migration |
|---------|-----------|----------|----------------|
| ODF (Ceph RBD) | Yes | Yes (CephFS) | Yes |
| HPE CSI | NFS Provisioner | Yes | Yes (NFS) |
| Dell CSI | No (v2.11) | NFS only | Limited |
| NetApp Trident | Yes (iSCSI/NVMe) | Yes (NFS) | Yes |
| IBM Block CSI | v1.12 beta | No | Limited |
| Portworx | Coming Q1/25 | Yes | Limited |
| KubeSAN | Yes | Yes | Yes |

Read `references/csi-comparison.md` for detailed vendor capabilities.

## Step 4: Configure Storage

Based on the chosen approach, provide:
1. Operator installation steps
2. StorageClass YAML
3. Default StorageClass annotation
4. Test PVC to verify
5. DR configuration (if needed)

Read `references/dr-options.md` for disaster recovery architectures.
