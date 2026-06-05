---
name: capacity-analyzer
description: >-
  Analyzes OpenShift Virtualization cluster capacity for migration planning.
  Evaluates current resource utilization (CPU, memory, storage), available
  headroom, and determines how many additional VMs can be migrated based
  on their resource profiles.
---

# Capacity Analyzer Instructions

When asked about cluster capacity or migration planning, analyze the
available resources.

## Step 1: Gather Cluster Resources

Collect from the target OCP Virt cluster:
- **Nodes**: Count, CPU cores, memory per node
- **Current utilization**: CPU/memory requests vs allocatable
- **Existing VMs**: Count, resource consumption
- **Storage**: Available PV capacity per StorageClass
- **Network**: Available IP ranges, VLAN capacity

## Step 2: Calculate Available Headroom

Read `references/capacity-formulas.md` for calculation methods.

For each resource type:
- **CPU headroom** = Total allocatable - Current requests - Reserved (20% buffer)
- **Memory headroom** = Total allocatable - Current requests - Reserved (20% buffer)
- **Storage headroom** = Total PV capacity - Current PVC usage

## Step 3: VM Resource Profiling

Categorize VMs by resource profile:
- **Small**: 1-2 vCPU, <4GB RAM, <50GB disk
- **Medium**: 2-4 vCPU, 4-16GB RAM, 50-200GB disk
- **Large**: 4-8 vCPU, 16-64GB RAM, 200-500GB disk
- **XLarge**: 8+ vCPU, 64GB+ RAM, 500GB+ disk

## Step 4: Capacity Projection

Calculate:
- How many VMs of each profile can fit
- When cluster will reach 80% utilization
- Whether node expansion is needed
- Storage provisioning requirements

## Step 5: Output

Present as:
1. Current cluster utilization summary
2. Available capacity by resource type
3. VM capacity by profile size
4. Recommendations for scaling
5. Risk factors (single points of failure, resource contention)
