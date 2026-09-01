---
name: network-architect
description: >-
  Designs target network architecture for OpenShift Virtualization deployments.
  Covers NIC bonding, OVN-K localnet and layer2 topologies, SR-IOV for high
  performance, dedicated migration networks, and production design patterns.
  Provides YAML examples for NMState, NADs, and bridge mappings.
---

# Network Architecture for OCP Virtualization

Help the user design their target VM network architecture on OpenShift.

## Step 1: Understand Current VMware Network

Ask the user about their current VMware networking:
- How many VLANs do VMs use?
- Are VMs on DVS or standard vSwitch?
- Do any VMs need SR-IOV or DPDK?
- Is there a dedicated vMotion network?
- What bonding/teaming is used on ESXi hosts?

## Step 2: Design Target Topology

Read `references/design-patterns.md` for common production topologies.

### Physical Network Configuration Wizard (OCP 4.21)

OCP 4.21 introduces a **UI-based physical network configuration wizard** that simplifies
NIC bonding, bridging, and VLAN configuration. Instead of writing NMState YAML manually,
administrators can configure node networking through the OCP console. Recommend using the
wizard for customers on OCP 4.21+ who prefer a GUI-driven approach.

Typical production layout:
- **bond0** (LACP): Machine network (OCP cluster traffic)
- **bond1** (LACP): VM live migration network
- **bond2** (LACP): ODF storage public network (if using ODF with Multus)
- **bond3** (LACP): ODF storage cluster network
- **bond4** (LACP): VM VLAN-tagged networks (via OVS bridge)

## Step 3: Configure with NMState

Read `references/nmstate-examples.md` for bond, bridge, and VLAN YAML examples.

Key rules:
- Use bond mode 1 (active-backup) or 4 (802.3ad/LACP)
- Never use mode 5/6 with OVS bridges
- Create OVS bridges with `allow-extra-patch-ports: true` for localnet
- One bridge mapping NNCP per localnet network

## Step 4: Create NADs for VM Networks

Read `references/nad-examples.md` for NetworkAttachmentDefinition templates.

Three topology choices:
- **localnet**: VLAN-tagged, external connectivity via OVS bridge (most common)
- **layer2**: overlay, VM-to-VM only, no external egress
- **User-Defined Tenant Networks (UDN)** (OCP 4.21): namespace-scoped overlay or routable L2 networks with built-in isolation

### User-Defined Tenant Networks (OCP 4.21)

UDN provides namespace-level network isolation without requiring manual NAD creation per VLAN:
- **Overlay UDN**: Namespace-scoped overlay network with automatic isolation from other namespaces
- **Routable L2 UDN**: L2 network that can be routed externally, with namespace-level boundaries
- Simplifies multi-tenant VM networking by replacing per-VLAN NAD management with declarative namespace networks
- Ideal for environments where each team/tenant needs isolated VM networks

### Simplified NAD Creation (OCP 4.21)

OCP 4.21 simplifies NAD creation through the console UI:
- Visual network topology selection (localnet vs layer2 vs UDN)
- Automatic subnet allocation and IPAM configuration
- Integration with the physical network wizard for end-to-end configuration

## Step 5: Output

Provide the user with:
1. Network topology diagram (ASCII or description)
2. NMState NNCP YAML for bonds and bridges (or wizard instructions for OCP 4.21+)
3. NAD YAML for each VM network (or UDN YAML for tenant networks on 4.21+)
4. Migration network NAD (if needed)
5. Verification commands
