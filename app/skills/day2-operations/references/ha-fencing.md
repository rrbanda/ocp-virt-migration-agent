# High Availability and Fencing for VMs

## Automatic VM Restart (Built-in)

OCP automatically reschedules VM pods to healthy nodes when a node fails. The restart time depends on the node failure detection timeout (~5 minutes by default).

Set `evictionStrategy: LiveMigrate` on the VM to automatically live migrate during planned node drain:

```yaml
spec:
  evictionStrategy: LiveMigrate
```

## Pod Disruption Budgets

Protect critical VMs from node drain during upgrades or maintenance:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: protect-database-vm
spec:
  minAvailable: 1
  selector:
    matchLabels:
      kubevirt.io/domain: database-vm
```

## Anti-Affinity (Spread VMs Across Hosts)

Keep related VMs (e.g., app server and its replica) on different nodes:

```yaml
spec:
  template:
    metadata:
      labels:
        app: web-tier
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: web-tier
                topologyKey: kubernetes.io/hostname
```

## Node Affinity (Pin VM to Specific Nodes)

Lock a VM to nodes with specific labels (e.g., GPU nodes, high-memory nodes):

```yaml
spec:
  template:
    spec:
      nodeSelector:
        node-role.kubernetes.io/virt-worker: ""
```

## Important: HA is NOT vSphere HA

In VMware, HA provides sub-minute failover via vCenter coordination. In OCP:
- Node failure detection: ~5 minutes (K8s default node monitor)
- VM restart: Additional ~30-60 seconds for pod scheduling and boot
- Total failover time: ~6 minutes (not sub-minute)

For faster failover, consider:
- Shorter `node-monitor-grace-period` (reduces detection time)
- Pre-pulled VM images (reduces startup time)
- Application-level HA (active-passive clustering inside VMs)
