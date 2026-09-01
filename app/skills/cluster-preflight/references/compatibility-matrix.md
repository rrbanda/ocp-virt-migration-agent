# MTV and OCP Version Compatibility Matrix

## MTV 2.10 / 2.11 Supported Platforms

### Target OpenShift Versions

| MTV Version | OCP 4.17 | OCP 4.18 | OCP 4.19 | OCP 4.20 |
|-------------|----------|----------|----------|----------|
| MTV 2.10.x | No | Yes | Yes | Yes |
| MTV 2.11.x | No | Yes | Yes | Yes |

### Target OpenShift Virtualization Versions

| MTV Version | OCP Virt 4.17 | OCP Virt 4.18 | OCP Virt 4.19 | OCP Virt 4.20 |
|-------------|---------------|---------------|---------------|---------------|
| MTV 2.10.x | No | Yes | Yes | Yes |
| MTV 2.11.x | No | Yes | Yes | Yes |

### Source Hypervisor Versions

| Source | Supported Versions | Notes |
|--------|-------------------|-------|
| VMware vSphere | 6.5 or later | vSphere 7 is EOL (Oct 2, 2025) but still supported as a migration source |
| Red Hat Virtualization (RHV) | 4.4 SP1 or later | RHV is EOL; migrate to OCP Virt |
| OpenStack | 16.1 or later | Red Hat OpenStack Platform |
| OVA files | Local OVA import (MTV 2.11.1+ GA) | Direct import from local machine |
| OCP Virt (live migration) | 4.20+ | Cross-cluster live migration (source must also be OCP Virt) |

## Migration Type Availability by Source

| Migration Type | VMware | RHV | OpenStack | OVA | OCP Virt |
|---------------|--------|-----|-----------|-----|----------|
| Cold | GA | GA | GA | GA (2.11.1+) | N/A |
| Warm (CBT) | GA (2.8+) | GA (2.8+) | No | No | N/A |
| Live (zero-downtime) | No | No | No | No | GA (2.10+) |
| Storage copy offload | GA (2.11, Dell/Infinidat) | No | No | No | No |

## Feature Availability by MTV Version

| Feature | MTV 2.10 | MTV 2.11.0 | MTV 2.11.1 | MTV 2.11.3 | MTV 2.11.5 | MTV 2.11.7 |
|---------|----------|-----------|-----------|-----------|-----------|-----------|
| Cold migration | GA | GA | GA | GA | GA | GA |
| Warm migration (VMware/RHV) | GA | GA | GA | GA | GA | GA |
| Live migration (OCP-to-OCP) | GA | GA | GA | GA | GA | GA |
| Storage copy offload | No | GA | GA | GA | GA | GA |
| OVA import (local) | TP | TP | GA | GA | GA | GA |
| Custom ServiceAccount | No | No | No | GA | GA | GA |
| Selective shared disk attach | No | No | No | GA | GA | GA |
| LUN device mapping (RDM offload) | No | No | No | GA | GA | GA |
| Windows static IP (no DHCP) | No | No | No | No | Dev Preview | Dev Preview |
| Multi-NIC to single NAD mapping | No | No | No | No | No | GA |

## Pre-Flight Compatibility Checks

Before starting a migration project, verify:

1. **MTV version matches OCP version**: MTV 2.10/2.11 requires OCP 4.18, 4.19, or 4.20
2. **OCP Virt operator version**: Should match the OCP version (e.g., OCP 4.20 -> OCP Virt 4.20)
3. **Source vSphere version**: 6.5 or later (check: `vCenter -> Help -> About`)
4. **VDDK compatibility**: VDDK version must match or be compatible with vCenter version
5. **For warm migration**: CBT must be available (vSphere 6.5+), VDDK required
6. **For live migration**: Both source and target must run OCP Virt 4.20+
7. **For storage copy offload**: MTV 2.11+, supported array (Dell PowerStore/PowerFlex or Infinidat InfiniBox)
