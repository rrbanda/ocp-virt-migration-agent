# Wave Planning Guide

## Wave 0: Practice Run (Non-Production)

Purpose: Validate the migration process before touching production.

- Select 3-5 dev/test VMs
- Execute the full migration workflow
- Validate the process, timing, and tooling
- Document lessons learned
- Refine procedures for production waves

## Wave 1-2: Low-Risk Production

Selection criteria:
- Simple RHEL 8/9 or Rocky 8/9 VMs
- Single disk < 200 GB
- No NFS mounts
- Verified recent backup
- Non-customer-facing
- Single network (no complex VLAN requirements)

## Wave 3-N: Medium-Risk Production

Selection criteria:
- Larger disks (200-500 GB)
- Multiple network interfaces
- Application dependencies (migrate the group together)
- Some NFS mounts (verify remote-fs.target)

## Final Wave: High-Risk / Critical

Selection criteria:
- Databases (ensure consistent backup first)
- VMs with complex networking (multiple VLANs, load balanced)
- AD-integrated services
- Customer-facing applications (plan for minimal downtime)

## Wave Schedule Template

| Wave | VMs | Risk | Change Window | Validation Period |
|------|-----|------|---------------|-------------------|
| Wave 0 | 3-5 dev/test | Low | Tuesday 2pm-6pm | 24h |
| Wave 1 | 5-10 low-risk prod | Low | Thursday 6pm-10pm | 48h (over weekend) |
| Wave 2 | 5-10 low-risk prod | Low | Tuesday 6pm-10pm | 24h |
| Wave 3 | 10-15 medium-risk | Medium | Thursday 6pm-midnight | 48h |
| Wave 4 | 10-15 medium-risk | Medium | Tuesday 6pm-midnight | 24h |
| Wave N | 5-10 critical | High | Friday 6pm-midnight | Weekend monitoring |

## Pacing Rules

- Minimum 24h between waves (for validation and burn-in)
- 48h between waves for high-risk VMs
- Never schedule two waves in the same change window
- Max 3-5 concurrent disk transfers (to avoid saturating network)
- Weekend waves for critical workloads (more monitoring time)
