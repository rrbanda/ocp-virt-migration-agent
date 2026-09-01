# Storage Decision Tree

## Question 1: Do you have existing enterprise SAN storage?

**YES** -> Does the vendor have a certified CSI driver for OCP?
  - **YES** -> Does the CSI driver support RWX for live migration?
    - **YES** -> Use vendor CSI driver as primary storage
    - **NO** -> Use vendor CSI for RWO workloads + ODF for RWX
  - **NO** -> Consider ODF or KubeSAN

**NO** -> Do you have local NVMe/SSD disks in worker nodes?
  - **YES** -> Use ODF internal (HCI) mode
  - **NO** -> You need to add storage (local disks, SAN, or cloud volumes)

## Question 2: How many VMs and what total disk capacity?

- **< 50 VMs, < 5 TB**: ODF internal (HCI) on 3 workers is sufficient
- **50-200 VMs, 5-50 TB**: ODF internal with dedicated storage nodes, or external Ceph
- **200+ VMs, 50+ TB**: ODF external mode with dedicated Ceph cluster

## Question 3: Do you need disaster recovery?

- **No DR**: Any storage option works
- **Metro DR (RPO=0)**: ODF with stretched Ceph cluster (< 10ms RTT)
- **Regional DR (RPO > 5min)**: ODF with async replication between clusters

## ODF Deployment Models

| Model | Description | When to Use |
|-------|-------------|-------------|
| Internal/HCI | ODF pods on same nodes as VMs | Small-medium, simplicity |
| Internal/Dedicated | ODF pods on separate infra nodes | Medium-large, isolation |
| External | ODF connects to standalone Ceph cluster | Large scale, performance |

## Replica Considerations

- **3 replicas** (default): Maximum data protection, 3x raw capacity
- **2 replicas**: Better performance, less capacity overhead, reduced protection
  - Available for block (RBD) in ODF 4.16+
  - CephFS 2-replica is dev preview in 4.16
  - Cannot protect against bit-flip errors
  - Slower recovery (single source)
