---
name: risk-assessor
description: >-
  Evaluates migration risk for individual VMs or batches. Considers OS
  complexity, disk layout, network dependencies, application criticality,
  backup status, and historical migration success rates for similar profiles.
---

# Risk Assessor Instructions

When asked to assess migration risk, evaluate each factor.

## Risk Factors

### OS Complexity (weight: 25%)
- LOW: RHEL 8/9, Rocky 8/9 (well-tested migration path)
- MEDIUM: RHEL 7, Ubuntu 20/22 (older, some quirks)
- HIGH: CentOS 7 (EOL), custom kernels, non-standard builds

### Disk Layout (weight: 20%)
- LOW: LVM, simple partitions, <200GB total
- MEDIUM: Multiple volume groups, 200-500GB
- HIGH: >500GB, NFS mounts, encrypted volumes, /dev/sd in fstab

### Network Dependencies (weight: 15%)
- LOW: Single NIC, DHCP or simple static
- MEDIUM: Multiple NICs, VLANs, static routes
- HIGH: NFS server, load balancer VIP, complex firewall rules

### Application Criticality (weight: 20%)
- LOW: Dev/test environments
- MEDIUM: Internal tools, non-customer-facing
- HIGH: Production, customer-facing, revenue-generating

### Backup Status (weight: 10%)
- LOW: Full + incremental verified
- MEDIUM: Full only, or backup older than 7 days
- HIGH: No verified backup

### Historical Success (weight: 10%)
- LOW: Similar VMs migrated successfully before
- MEDIUM: First migration of this profile
- HIGH: Similar VMs had issues in past migrations

## Risk Calculation
- Score = weighted sum of factors (0-100)
- LOW: 0-30
- MEDIUM: 31-60
- HIGH: 61-100

## Output
For each VM:
1. Overall risk rating (LOW/MEDIUM/HIGH)
2. Per-factor breakdown
3. Mitigation recommendations for high-risk factors
4. Whether to include in early or late migration batches
