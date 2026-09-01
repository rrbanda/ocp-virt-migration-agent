# CSI Driver Comparison for OCP Virtualization

## HPE CSI Driver

- **Supports**: Alletra, Nimble, Primera, 3PAR
- **Protocols**: FC, iSCSI
- **RWX**: Via NFS Server Provisioner (file mode only)
- **KubeVirt support**: Yes
- **Install**: Helm or OperatorHub
- **Quirk**: FC-only arrays with RWX block need `group --edit --iscsi_enabled yes` on Array OS CLI
- **Latest**: v2.5.1, supports OCP 4.16

## Dell CSI Driver

- **Supports**: PowerMax, PowerStore, PowerFlex, PowerScale, Unity XT
- **Protocols**: FC, iSCSI, NVMe/TCP
- **RWX**: PowerScale (NFS), PowerFlex limited
- **KubeVirt support**: Yes (most products)
- **Install**: OperatorHub
- **Quirk**: NVMe mounts on PowerStore fail in v2.11; use v2.10.1
- **Latest**: v2.11.0, supports OCP 4.15-4.16

## NetApp Trident CSI Driver

- **Supports**: ONTAP, E-Series, SolidFire
- **Protocols**: NFS, iSCSI, NVMe/TCP (FC coming Q1 2025)
- **RWX**: Yes (iSCSI/NVMe for block, NFS for file)
- **KubeVirt support**: Yes, explicitly supported
- **Install**: Manual, Operator, or Helm
- **Backup**: Trident Protect (replacing Astra Control) -- free
- **Latest**: v24.06, supports OCP 4.16

## IBM Block CSI Driver

- **Supports**: Spectrum Virtualize (FlashSystem, SVC)
- **Protocols**: iSCSI, FC, NVMe/FC
- **RWX**: v1.12 beta only
- **KubeVirt support**: Limited (RWO only for block)
- **Install**: OperatorHub
- **Latest**: v1.11.3, supports OCP 4.14-4.15

## Portworx

- **Install**: OperatorHub
- **Protocols**: Internal replication
- **RWX**: File-based only (block RWX for Flash Array coming Oct 2024, PX volumes Q1/25)
- **KubeVirt support**: PX CSI does NOT support KubeVirt
- **Assessment**: Directed Availability for OCPv (requires questionnaire)
- **Latest**: Operator 24.1.1, PX 3.1.3

## KubeSAN

- **What**: CSI plugin using shared SAN LUN as LVM volume group
- **RWX**: Yes (block)
- **KubeVirt support**: Yes
- **Best for**: When no vendor CSI available or org restrictions
- **Limitation**: Manual recovery after power failure
