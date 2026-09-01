# NMState Configuration Examples

## LACP Bond for VM Networks

```yaml
apiVersion: nmstate.io/v1
kind: NodeNetworkConfigurationPolicy
metadata:
  name: bond-vm-network
spec:
  nodeSelector:
    node-role.kubernetes.io/worker: ''
  desiredState:
    interfaces:
      - name: bond1
        type: bond
        state: up
        mtu: 9000
        ipv4:
          enabled: false
        link-aggregation:
          mode: 802.3ad
          options:
            miimon: '100'
          port:
            - eth2
            - eth3
```

## OVS Bridge for VM Localnet

```yaml
apiVersion: nmstate.io/v1
kind: NodeNetworkConfigurationPolicy
metadata:
  name: br-data
spec:
  nodeSelector:
    node-role.kubernetes.io/worker: ''
  desiredState:
    interfaces:
      - name: br-data
        type: ovs-bridge
        state: up
        mtu: 9000
        ipv4:
          enabled: false
        bridge:
          allow-extra-patch-ports: true
          options:
            stp: false
          port:
            - name: bond1
```

## Bridge Mapping for Localnet Network

One NNCP per VLAN-tagged localnet network:

```yaml
apiVersion: nmstate.io/v1
kind: NodeNetworkConfigurationPolicy
metadata:
  name: vlan100-br-data
spec:
  nodeSelector:
    node-role.kubernetes.io/worker: ''
  desiredState:
    ovn:
      bridge-mappings:
        - localnet: vlan100-br-data
          bridge: br-data
          state: present
```

## Migration Network (macvlan on dedicated bond)

```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: migration-network
  namespace: openshift-cnv
spec:
  config: |-
    {
      "cniVersion": "0.3.1",
      "type": "macvlan",
      "master": "bond1",
      "mode": "bridge",
      "ipam": {
        "type": "whereabouts",
        "range": "192.168.10.0/24",
        "exclude": ["192.168.10.1/32"]
      }
    }
```
