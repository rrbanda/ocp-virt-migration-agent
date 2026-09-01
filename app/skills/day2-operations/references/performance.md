# Performance Optimization for VMs

## Hugepages

Hugepages reduce TLB misses for memory-intensive VMs (databases, caches).

### Step 1: Label worker nodes
```bash
oc get nodes -l node-role.kubernetes.io/worker -o name | xargs -I{} oc label {} node-role.kubernetes.io/worker-hp=
```

### Step 2: Create TuneD profile
```yaml
apiVersion: tuned.openshift.io/v1
kind: Tuned
metadata:
  name: hugepages
  namespace: openshift-cluster-node-tuning-operator
spec:
  profile:
    - data: |
        [main]
        summary=Boot time configuration for hugepages
        include=openshift-node
        [bootloader]
        cmdline_openshift_node_hugepages=default_hugepagesz=1G hugepagesz=1G hugepages=50
      name: openshift-node-hugepages
  recommend:
    - machineConfigLabels:
        machineconfiguration.openshift.io/role: "worker-hp"
      priority: 30
      profile: openshift-node-hugepages
```

### Step 3: Create MachineConfigPool
```yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: MachineConfigPool
metadata:
  name: worker-hp
  labels:
    worker-hp: ""
spec:
  machineConfigSelector:
    matchExpressions:
      - {key: machineconfiguration.openshift.io/role, operator: In, values: [worker, worker-hp]}
  nodeSelector:
    matchLabels:
      node-role.kubernetes.io/worker-hp: ""
```

This triggers a rolling reboot of labeled nodes.

### Step 4: Configure VM to use hugepages
```yaml
spec:
  domain:
    resources:
      requests:
        memory: "4Gi"
    memory:
      hugepages:
        pageSize: "1Gi"
```

## CPU Pinning

Dedicated CPU cores for latency-sensitive workloads.

### Step 1: Enable CPU Manager
```yaml
apiVersion: machineconfiguration.openshift.io/v1
kind: KubeletConfig
metadata:
  name: cpumanager-enabled
spec:
  machineConfigPoolSelector:
    matchLabels:
      custom-kubelet: cpumanager-enabled
  kubeletConfig:
    cpuManagerPolicy: static
    cpuManagerReconcilePeriod: 5s
```

### Step 2: Configure VM
```yaml
spec:
  template:
    spec:
      domain:
        cpu:
          dedicatedCpuPlacement: true
          isolateEmulatorThread: true  # optional: reserve extra CPU for QEMU I/O
```

**Warning**: `isolateEmulatorThread: true` disables live migration for that VM.

## NUMA Alignment

For maximum performance, align VM resources with NUMA topology:
- Use `dedicatedCpuPlacement: true` (above)
- Set VM memory to fit within a single NUMA node
- OCP automatically handles NUMA-aware scheduling when CPU Manager is enabled
