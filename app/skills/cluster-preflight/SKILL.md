---
name: cluster-preflight
description: >-
  Validates OpenShift cluster infrastructure readiness before VMware-to-OCP
  Virtualization migrations. Covers 60+ checks across hardware, networking,
  storage, operators, identity, and connectivity. Run this before your first
  migration wave to catch blockers early.
---

# Cluster Pre-Flight Validation

Before migrating any VMs, validate that the target OpenShift cluster meets
all infrastructure requirements. Use the `check_cluster_readiness` tool for
automated checks, and this skill for manual verification items.

## Step 1: Operator Readiness

Verify these operators are installed and healthy:

| Operator | Required? | How to Check |
|----------|-----------|-------------|
| OpenShift Virtualization | Yes | `oc get csv -n openshift-cnv` -- status must be Succeeded |
| Migration Toolkit for Virtualization (MTV) | Yes | `oc get csv -n openshift-mtv` -- ForkliftController must exist |
| OpenShift Data Foundation (if using ODF) | Conditional | `oc get csv -n openshift-storage` |
| NMState Operator | Recommended | Required for post-install network config (bonds, bridges) |
| SR-IOV Operator | Optional | Only if VMs need SR-IOV passthrough |

Read `references/operator-checklist.md` for detailed verification steps.

## Step 2: Hardware Validation

Minimum production sizing per node role:

| Role | Qty | CPU | RAM | Local Storage |
|------|-----|-----|-----|---------------|
| Control Plane | 3 | 8 cores | 64 GB | 120 GB |
| Worker (Virt) | 3+ | 8+ cores | 128+ GB | 120 GB + storage disks |

Verify on each worker node:
- BIOS virtualization extensions enabled (Intel VT-x / AMD-V)
- IOMMU enabled (for SR-IOV / device passthrough)
- Latest firmware on NICs, HBAs, and BIOS
- Boot from local disk (not iSCSI/SAN for OS)

Read `references/hardware-requirements.md` for vendor-specific guidance.

## Step 3: Network Validation

| Check | How | BLOCKER if Failed |
|-------|-----|-------------------|
| DNS resolution from all nodes | `dig api.<cluster>.<domain>` from each node | Yes |
| NTP sync across nodes | `chronyc tracking` on each node | Yes |
| All VLANs created and trunked | Verify on network switches | Yes |
| MTU consistent (typically 1500 or 9000) | Check switch ports AND node interfaces | Yes |
| VM network VLANs reachable | Ping test from worker nodes | Yes |
| Migration network configured | NAD in openshift-cnv namespace | Recommended |

Read `references/network-checklist.md` for complete networking pre-flight.

## Step 4: Storage Validation

| Check | How | BLOCKER if Failed |
|-------|-----|-------------------|
| At least one StorageClass exists | `oc get sc` | Yes |
| RWX support available (for live migration) | Check CSI driver or ODF | Yes for live migration |
| Default StorageClass set | `oc get sc` -- look for (default) annotation | Recommended |
| Storage capacity sufficient | Sum of VM disks < available PV capacity | Yes |
| HyperConverged CR configured | `oc get hyperconverged -n openshift-cnv` | Yes |

Read `references/storage-checklist.md` for ODF vs CSI driver details.

## Step 5: Identity and Access

| Check | Details |
|-------|---------|
| Authentication configured | htpasswd, LDAP, OIDC, or AD |
| RBAC roles for migration operators | Users need create/delete on MTV CRDs |
| Service accounts for automation | If using Ansible or CI/CD pipelines |

## Step 6: Version Compatibility

Read `references/compatibility-matrix.md` for the full MTV/OCP/source version matrix.

Key version requirements:
- MTV 2.10/2.11 requires **OCP 4.18, 4.19, or 4.20**
- Source VMware vSphere must be **6.5 or later**
- Warm migration (CBT) requires **MTV 2.8+** and VDDK
- Cross-cluster live migration requires **MTV 2.10+** and **OCP Virt 4.20+** on both clusters
- Storage copy offload requires **MTV 2.11+** and supported SAN array

## Step 7: MTV-Specific Readiness

| Check | How |
|-------|-----|
| VMware provider configured | `oc get providers -n <mtv-ns>` |
| Forklift inventory reachable | Check inventory Route or service |
| VDDK image available | Required for VMware migrations (mandatory for vSAN sources) |
| Network maps created | For each VM VLAN to migrate |
| Storage maps created | Map VMware datastores to OCP storage classes |

## Step 8: Produce Pre-Flight Report

Summarize all checks as:
- **READY**: All checks pass
- **READY WITH WARNINGS**: No blockers, some warnings
- **NOT READY**: One or more blockers found
- **Incomplete**: Some checks could not be performed (manual verification needed)

Use the `assessment-report-generator` skill for report formatting.
