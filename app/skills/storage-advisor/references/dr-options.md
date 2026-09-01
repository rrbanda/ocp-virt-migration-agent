# Disaster Recovery Options for OCP Virtualization

## Metro DR (RPO = 0, RTO = 5-15 min)

- ODF with external stretched Ceph cluster across 2 data centers + arbiter in 3rd site
- Synchronous replication
- Requirements: < 10ms RTT between data sites, < 100ms RTT to arbiter
- Bare metal or VMware only
- Block and file support
- OPP + ODF Advanced subscription required

## Regional DR (RPO > 5 min, RTO = 5-15 min)

- Two ODF internal-mode clusters with async replication
- No latency limitations
- WAN with non-overlapping networks (overlapping OK with ACM)
- Block and file support
- OPP + ODF Advanced subscription required

## Stretched OCP Cluster (RPO = 0, RTO = 5-15 min)

- Single OCP/ODF cluster across 2 data centers + arbiter in 3rd site
- Internal Ceph storage with synchronous replication
- Same requirements as Metro DR
- Simpler management (single cluster)

## Vendor-Specific DR

| Vendor | DR Capability |
|--------|--------------|
| NetApp Trident Protect | Snapshot + backup to S3, cross-cluster replication |
| Dell CSI | Replication module for PowerMax/PowerStore |
| HPE | Peer Persistence for Primera/Alletra |
| IBM | Global Mirror / Metro Mirror for FlashSystem |
