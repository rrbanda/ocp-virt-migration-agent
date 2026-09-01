---
name: day2-operations
description: >-
  Guides post-migration VM operations on OpenShift Virtualization. Covers
  VM templates, live migration, HA and fencing, hugepages, CPU pinning,
  snapshots, post-install networking, storage management, and Ansible
  automation. Designed for VMware admins operating VMs on OCP day-to-day.
---

# Day-2 VM Operations

After VMs are migrated, help customers operate them on OpenShift Virtualization.

## VM Templates

Create reusable templates from existing VMs or disk images:

1. **From existing VM**: Create DataVolume from the VM's boot PVC, then create DataSource + Template
2. **From disk image (qcow2)**: Upload to PVC via CDI, create DataSource + Template
3. **From registry**: Pull container disk image, create DataSource + Template

Read `references/templates.md` for step-by-step YAML examples.

## Live Migration

Move running VMs between worker nodes without downtime:
- Requires RWX storage (ODF Ceph RBD, NetApp Trident, or NFS-based)
- Configure dedicated migration network for isolation
- Use `virtctl migrate <vm-name>` or OCP console

### Cross-Cluster Live Migration (OCP Virt 4.20+ with MTV 2.10+)

Move running VMs between separate OCP Virt clusters with zero downtime:
- Both clusters must run OCP Virt 4.20+
- Uses MTV live migration type (distinct from intra-cluster live migration)
- Useful for cluster upgrades, capacity rebalancing, or DC migrations

### Storage Live Migration (OCP Virt 4.18+)

Move VM disks between StorageClasses while the VM is running:
- Equivalent of VMware Storage vMotion
- Use cases: migrate from ODF to vendor CSI, rebalance storage pools, evacuate failing storage
- No VM downtime during the operation

Read `references/live-migration.md` for configuration and troubleshooting.

## High Availability and Fencing

- VMs automatically restart on another node if the host fails (K8s pod rescheduling)
- Use **PodDisruptionBudget** to protect VMs during planned maintenance
- Use **affinity/anti-affinity** to spread critical VMs across hosts
- Use **evictionStrategy: LiveMigrate** to auto-migrate during node drain

Read `references/ha-fencing.md` for production HA configuration.

## Performance Optimization

- **Hugepages**: 1GB pages for memory-intensive VMs (requires TuneD + MCP)
- **CPU Pinning**: Dedicated CPU cores for latency-sensitive VMs (requires CPU Manager)
- **isolateEmulatorThread**: Reserve extra CPU for QEMU (disables live migration)

Read `references/performance.md` for configuration steps.

## Snapshots and Backup

- Create point-in-time snapshots with VirtualMachineSnapshot CR
- Restore to any previous snapshot with VirtualMachineRestore CR
- Integrate with backup solutions (Trident Protect, Velero, IBM Fusion)
- **Storage-agnostic CBT** (Tech Preview in OCP Virt 4.21): Change Block Tracking for incremental backups independent of storage backend -- reduces backup time and storage consumption

Read `references/snapshots.md` for examples.

## GPU Passthrough and MIG vGPU (OCP Virt 4.21)

- **Full GPU passthrough**: Dedicate an entire GPU to a single VM (existing feature)
- **MIG vGPU** (4.21): Share a single NVIDIA GPU across multiple VMs using Multi-Instance GPU
  - Each VM gets a guaranteed, isolated slice of GPU compute and memory
  - Requires NVIDIA A100, A30, or H100 GPUs with MIG-capable drivers
  - Configure via `gpus` section in the VM spec with MIG device resource names

## OpenShift Lightspeed Integration (OCP 4.21)

AI-assisted troubleshooting within the OCP console:
- Ask natural-language questions about VM issues, cluster state, and configuration
- Get guided remediation suggestions based on cluster context
- Useful for day-2 operations troubleshooting without deep K8s expertise

## Ansible Automation

Create and manage VMs programmatically:
- Use `kubernetes.core.k8s` Ansible module
- Jinja2 templates for VM specs
- Integrate with AAP/Tower for self-service provisioning

Read `references/ansible-automation.md` for playbook examples.
