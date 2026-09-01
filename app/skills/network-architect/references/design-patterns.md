# Production Network Design Patterns

## Pattern 1: Converged (Minimum NICs)

Two NICs bonded for all traffic. Simplest, suitable for smaller deployments.

```
Node:
  bond0 (eth0 + eth1, LACP)
    └── br-ex (OVS bridge)
          ├── Machine network (OCP cluster)
          ├── Pod network (OVN-K)
          └── VM networks (localnet NADs with VLAN tags)
```

Pros: Simple, minimum hardware
Cons: All traffic shares bandwidth, no isolation

## Pattern 2: Dedicated VM NICs (Recommended for Production)

Separate bond for VM traffic, isolating it from cluster traffic.

```
Node:
  bond0 (eth0 + eth1, LACP) -- Machine + Pod network
    └── br-ex (OVS bridge)

  bond1 (eth2 + eth3, LACP) -- VM networks
    └── br-data (OVS bridge, allow-extra-patch-ports: true)
          ├── VLAN 100: prod-app-network (localnet NAD)
          ├── VLAN 200: prod-db-network (localnet NAD)
          └── VLAN 300: mgmt-network (localnet NAD)
```

Pros: VM traffic isolated, better bandwidth
Cons: More NICs needed

## Pattern 3: Full Separation (Enterprise)

Separate bonds for machine, VM, migration, and storage.

```
Node:
  bond0 (eth0 + eth1) -- Machine + Pod network
  bond1 (eth2 + eth3) -- VM live migration
  bond2 (eth4 + eth5) -- ODF public network
  bond3 (eth6 + eth7) -- ODF cluster network
  bond4 (eth8 + eth9) -- VM VLAN networks
    └── br-data (OVS bridge)
```

Pros: Full isolation, maximum bandwidth per workload
Cons: Requires 10 NICs per node

## Pattern 4: SR-IOV for High Performance

Direct hardware passthrough for latency-sensitive VMs.

```
Node:
  bond0 -- Machine + Pod network
  eth2 (SR-IOV NIC) -- VFs passed directly to VMs
    ├── VF0 -> VM1
    ├── VF1 -> VM2
    └── VF2 -> VM3
```

Pros: Near-native network performance
Cons: Live migration limited, requires supported NICs

## Pattern 5: User-Defined Tenant Networks (OCP 4.21+)

Namespace-scoped networks with automatic isolation. Each tenant gets their own
network without shared VLAN infrastructure.

```
Namespace: team-a
  └── UDN (overlay or routable L2)
        ├── VM1 (team-a)
        └── VM2 (team-a)

Namespace: team-b
  └── UDN (overlay or routable L2)
        ├── VM3 (team-b)
        └── VM4 (team-b)

(team-a and team-b VMs are isolated by default)
```

Pros: Simplified multi-tenant isolation, no VLAN management, declarative
Cons: Requires OCP 4.21+, limited external routing options for overlay UDN
