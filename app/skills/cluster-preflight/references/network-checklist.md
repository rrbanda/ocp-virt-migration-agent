# Network Pre-Flight Checklist

## DNS (BLOCKER if not configured)

| Record | Value | Purpose |
|--------|-------|---------|
| `api.<cluster>.<domain>` | API VIP | K8s API access |
| `api-int.<cluster>.<domain>` | API VIP (or CNAME) | Internal API |
| `*.apps.<cluster>.<domain>` | Ingress VIP | Wildcard for routes |
| `<node>.<cluster>.<domain>` | Node IP | Per-node resolution |

Verify from each node:
```bash
dig +short api.<cluster>.<domain>
dig +short *.apps.<cluster>.<domain>
```

## NTP (BLOCKER if not synced)

All nodes must be synchronized within 1 second:
```bash
chronyc tracking  # on each node
```

## Network Infrastructure

| Check | Y/N | Notes |
|-------|-----|-------|
| All VLANs created on switches | | List VLAN IDs |
| VLANs trunked between switches | | Verify inter-switch links |
| SVIs/VLAN interfaces created | | For routed networks |
| Routes advertised for VM subnets | | If VMs need external access |
| MTU consistent (1500 or 9000) | | Check BOTH switch ports AND node interfaces |
| All node ports enabled on switches | | No disabled ports |
| Same L2 domain for all worker nodes | | Required for OVN-K |

## NIC Configuration

Supported bonding modes for OCP:
- **Mode 1 (active-backup)**: No switch config needed. Simplest.
- **Mode 2 (balance-xor)**: Requires static EtherChannel on switch.
- **Mode 4 (802.3ad/LACP)**: Requires LACP on switch. Best throughput.

Modes that DO NOT WORK with bridges (do not use for VM networks):
- Mode 0 (balance-rr): packet order not guaranteed
- Mode 5 (balance-tlb): incompatible with OVS bridges
- Mode 6 (balance-alb): incompatible with OVS bridges

## VM Network Requirements

For each VLAN that VMs will use:
1. VLAN must be trunked to all worker node switch ports
2. NetworkAttachmentDefinition (NAD) must be created in the VM namespace
3. If using OVN-K localnet: OVS bridge + bridge mapping NNCP required
4. If using SR-IOV: SriovNetworkNodePolicy + SriovNetwork required

## Migration Network (Recommended)

A dedicated network for VM live migration:
- Separate bond or NIC from VM traffic
- NAD in `openshift-cnv` namespace
- Configured in HyperConverged CR `liveMigrationConfig.network`
- macvlan type with whereabouts IPAM
