---
name: vmware-feature-mapper
description: >-
  Translates VMware vSphere concepts to OpenShift Virtualization equivalents.
  Covers networking (DVS to OVN-K), storage (VMDK to PVC), compute (vCPU to
  CPU requests), HA (DRS to descheduler), templates, snapshots, and monitoring.
  Designed for VMware administrators learning OpenShift Virtualization.
---

# VMware Feature Mapping

When a user asks "how do I do X in OpenShift Virt?" or "what's the equivalent
of VMware Y?", use this mapping to provide an accurate, actionable answer.

Read `references/feature-map.md` for the complete mapping table.

## How to Use This Skill

1. Identify the VMware feature the user is asking about
2. Look up the OpenShift Virtualization equivalent in the feature map
3. Provide the OCP Virt approach with a brief explanation of differences
4. If the user needs step-by-step configuration, load the relevant reference:
   - Networking: load `network-architect` skill
   - Storage: load `storage-advisor` skill
   - Compute/HA: load `day2-operations` skill
5. If the user mentions VMware licensing, cost concerns, or EOL timelines:
   - Read `references/vmware-eol-context.md` for current EOL dates and licensing changes
   - vSphere 7 is **EOL since October 2, 2025** -- no patches or support
   - vSphere 8 EOL is October 11, 2027
   - Perpetual licenses are no longer renewable; subscription-only model
   - Mention **OpenShift Virtualization Engine** as a lower-cost VM-only option

## Key Differences to Communicate

- OpenShift Virt VMs are **Kubernetes pods** -- they follow K8s lifecycle, scheduling, and networking
- There is no vCenter equivalent -- use the **OCP console**, **CLI**, or **ACM** for multi-cluster management
- YAML is the configuration language -- but the OCP console provides GUI for most operations (OCP 4.21 adds a physical network configuration wizard)
- VM templates use **DataSource + Template** CRDs, not VM cloning
- Storage is **PVC-based** -- no VMFS/vSAN datastores, instead StorageClasses and PersistentVolumes
- Storage live migration (4.18+) lets you move VM disks between StorageClasses while running -- similar to Storage vMotion
- Networking uses **Multus + OVN-K** for multi-network VMs, not DVS port groups
- OCP 4.21 adds **User-Defined Tenant Networks (UDN)** for overlay and routable L2 isolation
- **MIG vGPU** (4.21) shares physical GPUs across VMs, similar to VMware vSGA but using NVIDIA Multi-Instance GPU
- **OpenShift Virtualization Engine** is a VM-only OCP edition at lower cost -- good for customers who only want virtualization, not containers
