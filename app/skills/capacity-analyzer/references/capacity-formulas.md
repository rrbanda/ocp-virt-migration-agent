# Capacity Planning Formulas

## CPU Capacity
- Allocatable CPU = Sum of all worker node allocatable CPU
- Used CPU = Sum of all pod CPU requests
- Buffer = 20% of allocatable (for burst and system workloads)
- Available CPU = Allocatable - Used - Buffer

## Memory Capacity
- Allocatable Memory = Sum of all worker node allocatable memory
- Used Memory = Sum of all pod memory requests
- Buffer = 20% of allocatable
- Available Memory = Allocatable - Used - Buffer
- Note: VMs use guaranteed QoS, so requests = limits

## Storage Capacity
- Total = Sum of StorageClass capacity
- Used = Sum of bound PVC sizes
- Available = Total - Used
- Note: Account for VM snapshots (2x disk size recommended)

## VM Fit Calculation
- VMs that fit = min(Available CPU / VM CPU, Available Memory / VM Memory)
- Consider anti-affinity rules (VMs spread across nodes)
- Consider live migration overhead (temporary 2x memory during migration)

## Batch Size Recommendation
- Maximum concurrent migrations = min(Available bandwidth / per-VM bandwidth, cluster spare capacity / per-VM resource)
- Recommended: 5-10 VMs per batch for medium clusters
- Allow 24h between batches for validation
