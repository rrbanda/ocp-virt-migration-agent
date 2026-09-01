# Hardware Requirements for OCP Virtualization

## Minimum Production Sizing

| Role | Qty | CPU Cores | RAM | Boot Disk | Additional Storage |
|------|-----|-----------|-----|-----------|-------------------|
| Control Plane | 3 | 8 | 64 GB | 120 GB SSD | None |
| Worker (Virt) | 3+ | 8+ | 128+ GB | 120 GB SSD | ODF or external |
| Infrastructure (optional) | 3 | 8 | 64 GB | 120 GB SSD | ODF disks |

## BIOS/Firmware Checklist

For each worker node that will host VMs:

- [ ] Intel VT-x or AMD-V enabled in BIOS
- [ ] Intel VT-d or AMD-Vi (IOMMU) enabled (required for SR-IOV/passthrough)
- [ ] Latest BIOS version from vendor
- [ ] Latest NIC firmware
- [ ] Latest HBA/storage controller firmware
- [ ] Boot order: local disk first
- [ ] No bootable USB or CD media

## Supported Hardware

Tested configurations from real deployments:

| Vendor | Model | Notes |
|--------|-------|-------|
| HPE | ProLiant DL360/DL380 Gen10+ | Widely deployed, excellent compatibility |
| HPE | BL460c Gen10 (blade) | Tested at Government of Alberta |
| Dell | PowerEdge R640/R740 | Common in enterprise deployments |
| Lenovo | ThinkSystem SR650 | Validated with OCP |

## Capacity Planning

When sizing worker nodes for VM workloads:

- **CPU overcommit**: 4:1 is typical for non-CPU-intensive VMs. Use 1:1 for production databases.
- **Memory**: No overcommit recommended. VMs get guaranteed memory (QoS).
- **Storage**: Account for VM disk + 20% overhead for snapshots and thin provisioning.
- **Network**: 10 GbE minimum. 25 GbE recommended for storage-heavy workloads.
