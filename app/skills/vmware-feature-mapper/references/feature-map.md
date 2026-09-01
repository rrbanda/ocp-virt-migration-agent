# VMware to OpenShift Virtualization Feature Map

## Networking

| VMware Feature | OpenShift Virt Equivalent | Notes |
|----------------|--------------------------|-------|
| vSphere Distributed Switch (DVS) | OVN-Kubernetes (OVN-K) | Default SDN since OCP 4.12 |
| DVS port group with VLAN | OVN-K localnet NAD with VLAN tag | Requires OVS bridge + bridge mapping |
| Intra-host VM network (no uplink) | OVN-K layer2 network | Overlay, VM-to-VM only, no egress |
| NSX micro-segmentation | MultiNetworkPolicy on OVN-K networks | Per-VM network policy |
| NSX routing/L3 isolation | ISV partners (Cisco ACI, Juniper, Tigera) | OVN-K has limited L3 |
| vMotion network | Dedicated migration NAD in openshift-cnv | macvlan with whereabouts IPAM |
| vSwitch port group | NetworkAttachmentDefinition (NAD) | Multus manages multi-NIC VMs |
| VM NIC | Additional interface via Multus NAD | Pod network + secondary NICs |

## Storage

| VMware Feature | OpenShift Virt Equivalent | Notes |
|----------------|--------------------------|-------|
| VMDK disk | PersistentVolumeClaim (PVC) | Block or filesystem mode |
| VMFS datastore | StorageClass + PVs | CSI driver provisions PVs |
| vSAN | OpenShift Data Foundation (ODF) | Ceph-based, integrated lifecycle |
| RDM (Raw Device Mapping) | Block PV with `volumeMode: Block` | Direct block device access |
| Storage vMotion | PVC migration (manual) | Not automatic like VMware |
| Thin provisioning | CSI thin provisioning | Depends on storage backend |
| VAAI offload | CSI clone/snapshot | Backend-specific acceleration |

## Compute

| VMware Feature | OpenShift Virt Equivalent | Notes |
|----------------|--------------------------|-------|
| vCPU | `spec.domain.cpu.cores/sockets/threads` | Maps to K8s CPU requests |
| Memory reservation | `spec.domain.resources.requests.memory` | Guaranteed QoS (no overcommit) |
| CPU affinity | `dedicatedCpuPlacement: true` | Requires CPU Manager enabled |
| Hugepages | TuneD profile + VM `spec.domain.memory.hugepages` | Requires MachineConfigPool |
| NUMA affinity | Node selector + CPU pinning | For latency-sensitive workloads |
| Hot-add CPU/memory | Not supported | Requires VM restart |
| VM hardware version | Not applicable | KubeVirt uses libvirt/QEMU |

## High Availability

| VMware Feature | OpenShift Virt Equivalent | Notes |
|----------------|--------------------------|-------|
| vSphere HA | Automatic VM restart on node failure | Built into K8s pod scheduling |
| DRS (load balancing) | Descheduler (Tech Preview) | Rebalances VM placement |
| VM affinity rules | `podAffinity` in VM spec | Label-based node/pod selection |
| VM anti-affinity rules | `podAntiAffinity` in VM spec | Keep VMs on separate hosts |
| Node drain protection | PodDisruptionBudget | Prevents drain during maintenance |
| Fault tolerance | Not available | Use HA + anti-affinity instead |
| Resource pools | Namespace quotas + LimitRanges | Per-namespace resource control |

## Templates and Lifecycle

| VMware Feature | OpenShift Virt Equivalent | Notes |
|----------------|--------------------------|-------|
| VM template | Template + DataSource + DataVolumeTemplate | YAML-based, parameterized |
| Clone VM | DataVolume clone from existing PVC | Source PVC -> new DataVolume |
| OVF/OVA import | Containerized Data Importer (CDI) | URL, registry, or upload |
| Snapshot | VirtualMachineSnapshot CR | Consistent snapshot of all disks |
| Restore from snapshot | VirtualMachineRestore CR | Point-in-time recovery |
| Content Library | openshift-virtualization-os-images namespace | Pre-loaded OS boot sources |

## Management and Monitoring

| VMware Feature | OpenShift Virt Equivalent | Notes |
|----------------|--------------------------|-------|
| vCenter Server | OCP Console + CLI | Single-cluster management |
| vCenter multi-cluster | Advanced Cluster Management (ACM) | Multi-cluster visibility |
| vRealize Operations | OCP Monitoring (Prometheus + Grafana) | Built-in metrics and dashboards |
| PowerCLI | `oc` CLI + `virtctl` | Kubernetes-native CLI tools |
| Ansible for VMware | Ansible `kubernetes.core` collection | K8s-native automation |
| vSphere API | Kubernetes API | All operations via standard K8s API |

## Migration

| VMware Feature | OpenShift Virt Equivalent | Notes |
|----------------|--------------------------|-------|
| V2V conversion | Migration Toolkit for Virtualization (MTV 2.11) | Forklift-based, automated |
| Cold migration | MTV cold migration (GA) | VM stopped during transfer |
| Warm migration | MTV warm migration (GA since 2.8) | CBT-based incremental copy, minutes of downtime at cutover |
| Cross-vCenter migration | MTV live migration (GA since 2.10) | Zero-downtime between OCP Virt clusters (requires 4.20+) |
| Storage vMotion | Storage live migration (GA in OCP Virt 4.18+) | Move VM disks between StorageClasses without downtime |
| P2V conversion | Not included | Use disk imaging tools |

## OCP Virtualization 4.18 – 4.21 Features

| Feature | GA Version | Description |
|---------|-----------|-------------|
| Cross-cluster live VM migration | 4.20+ (via MTV 2.10) | Zero-downtime migration of running VMs between OCP Virt clusters |
| Storage live migration | 4.18+ | Move VM disks between StorageClasses while VM is running |
| Storage-agnostic CBT | 4.21 (TP) | Change Block Tracking for incremental backups, independent of storage backend |
| MIG vGPU support | 4.21 | Share a single physical GPU across multiple VMs using NVIDIA MIG (Multi-Instance GPU) |
| OpenShift Lightspeed integration | 4.21 | AI-assisted troubleshooting and guidance within the OCP console |
| Physical network configuration wizard | 4.21 | UI-based NIC bonding, bridging, and VLAN configuration (replaces manual NMState YAML) |
| User-Defined Tenant Networks (UDN) | 4.21 | Overlay and routable L2 networks with namespace-level isolation |
| Windows Server 2025 SVVP | 4.21 | SVVP-validated support for Windows Server 2025 guests |
| vTPM with block storage | 4.21 | Virtual Trusted Platform Module with RWO block storage support |
| OpenShift Virtualization Engine | 4.18+ | VM-only OCP edition (128 cores/dual socket) at lower cost for VM-only workloads |
