# Go/No-Go Criteria for Migration Waves

## Pre-Wave Checklist (All Must Pass)

### Infrastructure
- [ ] Cluster pre-flight passes (use `check_cluster_readiness` tool)
- [ ] Target storage has sufficient capacity for all VMs in the wave
- [ ] Network maps and storage maps are configured for all VMs
- [ ] MTV providers are healthy and inventory is current

### Backup and Recovery
- [ ] All source VMs have verified backup (Full + Incremental within last 7 days)
- [ ] Rollback procedure documented and tested for this wave
- [ ] Source VMware environment confirmed stable (no active alerts)

### Change Management
- [ ] Change request submitted and approved by CAB
- [ ] Affected application owners notified
- [ ] Support team briefed on the migration window
- [ ] Escalation contacts identified and available

### Technical Readiness
- [ ] DNS change scripts prepared (not yet applied)
- [ ] Monitoring dashboards configured for target VMs
- [ ] Load balancer pool changes prepared (not yet applied)
- [ ] Post-migration validation checklist ready

## Decision Matrix

| Condition | Decision |
|-----------|----------|
| All checks pass | GO -- proceed with wave |
| 1-2 non-blocker items pending | GO WITH CAUTION -- proceed but monitor closely |
| Any blocker item fails | NO-GO -- postpone wave, resolve blockers |
| Infrastructure instability | NO-GO -- wait for stability |
| Key personnel unavailable | NO-GO -- reschedule to ensure coverage |

## During Execution

Abort the wave if:
- More than 20% of VMs fail to migrate
- Any critical/high-priority VM fails
- Cluster becomes unstable (node failures, storage issues)
- Migration is taking more than 2x the estimated time

## Post-Wave Sign-Off

All must be verified before closing the wave:
- [ ] All VMs in the wave are running on OCP Virt
- [ ] Application health checks pass
- [ ] DNS updated and verified
- [ ] Source VMs decommissioned (renamed, NICs disconnected, powered off)
- [ ] CMDB updated
- [ ] Migration record saved (use `record_migration` tool)
