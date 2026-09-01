# VMware vSphere EOL and Licensing Context

Understanding VMware's product lifecycle and licensing changes is critical for migration
conversations. This is the #1 driver for customer interest in OpenShift Virtualization.

## vSphere End-of-Life Timelines

| Product | End of General Support | End of Technical Guidance | Status |
|---------|----------------------|--------------------------|--------|
| vSphere 7.0 | **October 2, 2025** | November 2, 2027 | **EOL -- no patches, no support** |
| vSphere 8.0 | October 11, 2027 | November 11, 2029 | Active support |
| vSphere 9.0 | TBD | TBD | Only available inside VVF/VCF bundles (no standalone) |

### What EOL Means for Customers on vSphere 7

- No security patches after October 2, 2025
- No bug fixes or updates
- Support cases accepted only under Technical Guidance (best-effort, no fixes)
- Compliance frameworks (PCI-DSS, HIPAA, SOC2) may flag unsupported hypervisors
- Customers must either upgrade to vSphere 8 (subscription-only) or migrate off VMware

## Licensing Changes (Post-Broadcom Acquisition)

### Perpetual License Elimination
- VMware perpetual licenses can no longer be renewed for Support & Subscription (SnS)
- All new purchases and renewals require subscription licensing
- Existing perpetual license holders can continue running but cannot get patches without active SnS

### Product Consolidation
- **VMware vSphere Foundation (VVF)**: Entry-level bundle, replaces standalone vSphere
- **VMware Cloud Foundation (VCF)**: Full-stack bundle (vSphere + vSAN + NSX + Aria)
- Standalone vSphere, vSAN, and NSX are no longer sold separately
- **VVF withdrawn in several EMEA countries** -- VCF is the only option in those regions

### vSphere 9
- Only available as part of VVF or VCF bundles
- No standalone vSphere 9 purchase path
- Significant cost increase over standalone vSphere 7/8 licensing

## Migration Conversation Context

When a customer mentions VMware licensing pressure, cost concerns, or EOL:

1. **Acknowledge the urgency**: vSphere 7 is already EOL; vSphere 8 EOL is October 2027
2. **Present OpenShift Virtualization as an alternative**: Runs VMs on the same platform as containers
3. **Mention OpenShift Virtualization Engine**: VM-only OCP edition at lower cost (128 cores/dual socket) for customers who only want virtualization
4. **Highlight MTV maturity**: MTV 2.11 supports cold, warm, and live migration with automated conversion
5. **Address the storage question**: Existing SAN investments (HPE, Dell, NetApp, IBM) work with CSI drivers -- no storage rip-and-replace needed

## Common Customer Scenarios

### Scenario 1: vSphere 7 EOL (Urgent)
- Customer is running vSphere 7 with expired support
- Cannot get security patches
- Options: upgrade to vSphere 8 (subscription) or migrate to OCP Virt
- Migration recommendation: Start with non-critical VMs, build confidence, then migrate production

### Scenario 2: License Renewal Shock
- Customer receives renewal quote 3-5x higher than previous perpetual SnS
- Evaluating alternatives before next renewal
- Migration recommendation: Proof-of-concept with 5-10 VMs, then phased migration plan

### Scenario 3: VCF-Only Region
- Customer in EMEA region where VVF is withdrawn
- Must purchase full VCF stack or find alternative
- Migration recommendation: OCP Virt with existing SAN storage, avoiding VCF cost

### Scenario 4: Strategic Platform Consolidation
- Customer wants to run VMs and containers on one platform
- Already has or is evaluating OpenShift for cloud-native workloads
- Migration recommendation: Phased approach, starting with dev/test VMs
