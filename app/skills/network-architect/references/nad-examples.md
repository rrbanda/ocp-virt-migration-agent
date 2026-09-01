# NetworkAttachmentDefinition Examples

## OVN-K Localnet (VLAN-tagged, external connectivity)

```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: vlan100-prod
  namespace: vm-workloads
  annotations:
    description: Production network VLAN 100 via br-data bridge
spec:
  config: |-
    {
      "cniVersion": "0.3.1",
      "name": "vlan100-br-data",
      "type": "ovn-k8s-cni-overlay",
      "topology": "localnet",
      "netAttachDefName": "vm-workloads/vlan100-prod",
      "vlanID": 100,
      "subnets": "10.100.0.0/24",
      "excludeSubnets": "10.100.0.0/29"
    }
```

Requirements:
- OVS bridge with `allow-extra-patch-ports: true`
- Bridge mapping NNCP for `vlan100-br-data` -> `br-data`
- VLAN 100 trunked on switch ports to all workers
- `subnets` field requires OCP 4.16+ (enables port security)

## OVN-K Layer2 (overlay, VM-to-VM only)

```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: internal-cluster
  namespace: vm-workloads
spec:
  config: |-
    {
      "cniVersion": "0.3.1",
      "name": "internal-l2",
      "type": "ovn-k8s-cni-overlay",
      "topology": "layer2",
      "mtu": 1500,
      "netAttachDefName": "vm-workloads/internal-cluster"
    }
```

No external connectivity. Only VMs on the same layer2 network can communicate.

## SR-IOV Network

```yaml
apiVersion: sriovnetwork.openshift.io/v1
kind: SriovNetwork
metadata:
  name: sriov-prod
  namespace: openshift-sriov-network-operator
spec:
  resourceName: sriov_nic1
  networkNamespace: vm-workloads
  vlan: 100
  spoofChk: "on"
  trust: "off"
  ipam: |-
    {
      "type": "whereabouts",
      "range": "10.100.0.0/24",
      "exclude": ["10.100.0.1/32"]
    }
```

This creates a NAD in the `vm-workloads` namespace automatically.
