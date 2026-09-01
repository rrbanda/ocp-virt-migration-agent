# Storage Pre-Flight Checklist

## Minimum Requirements

| Requirement | Why | Check Command |
|-------------|-----|---------------|
| At least one StorageClass | VMs need persistent volumes | `oc get sc` |
| RWX support | Required for live migration | Check CSI driver docs |
| Sufficient capacity | Sum of all VM disks + 20% overhead | `oc get pv` + VM inventory |
| Default StorageClass set | Simplifies VM creation | `oc get sc -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}'` |

## Storage Options Decision

| Option | Best For | Live Migration | Complexity |
|--------|----------|---------------|------------|
| ODF (internal/HCI) | Most deployments | Yes (RWX via CephFS/RBD) | Medium |
| ODF (external Ceph) | Large scale, separate storage | Yes | Higher |
| Vendor CSI (HPE/Dell/NetApp) | Existing SAN investment | Check driver | Varies |
| KubeSAN | Shared SAN LUN | Yes (block RWX) | Lower |

## ODF Pre-Flight

If using ODF:
- [ ] Local Storage Operator installed (for internal mode)
- [ ] At least 3 worker nodes with local disks
- [ ] Disks are clean (no previous Ceph data -- `sgdisk --zap-all`)
- [ ] Multus NADs for ODF public and cluster networks (recommended)

## CSI Driver Pre-Flight

If using a vendor CSI driver:
- [ ] Driver installed and healthy (`oc get pods -n <driver-ns>`)
- [ ] StorageClass created and tested (`oc apply -f test-pvc.yaml`)
- [ ] RWX support verified (create a test RWX PVC)
- [ ] Multipathing configured if using FC/iSCSI
- [ ] Driver supports KubeVirt/OCP Virtualization (check vendor docs)

## Backup Solution

- [ ] Backup solution identified (IBM Fusion, Trident Protect, Velero, etc.)
- [ ] Backup of existing VMs verified before migration
- [ ] Restore procedure tested
