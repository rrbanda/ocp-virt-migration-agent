# VM Template Creation

## From an Existing VM Boot Disk

```yaml
# 1. Create DataVolume from existing PVC
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataVolume
metadata:
  name: rhel9-golden-pvc
  namespace: openshift-virtualization-os-images
spec:
  source:
    pvc:
      namespace: my-vms
      name: existing-vm-boot-disk
  pvc:
    volumeMode: Block
    accessModes:
      - ReadWriteOnce
    resources:
      requests:
        storage: 30Gi
```

```yaml
# 2. Create DataSource pointing to the golden PVC
apiVersion: cdi.kubevirt.io/v1beta1
kind: DataSource
metadata:
  name: rhel9-golden
  namespace: openshift-virtualization-os-images
spec:
  source:
    pvc:
      name: rhel9-golden-pvc
      namespace: openshift-virtualization-os-images
```

```yaml
# 3. Create Template with parameters
apiVersion: template.openshift.io/v1
kind: Template
metadata:
  name: rhel9-server
  namespace: openshift
  labels:
    template.kubevirt.io/type: vm
    os.template.kubevirt.io/rhel9: 'true'
  annotations:
    openshift.io/display-name: RHEL 9 Server
objects:
  - apiVersion: kubevirt.io/v1
    kind: VirtualMachine
    metadata:
      name: '${NAME}'
    spec:
      dataVolumeTemplates:
        - metadata:
            name: '${NAME}-root'
          spec:
            sourceRef:
              kind: DataSource
              name: rhel9-golden
              namespace: openshift-virtualization-os-images
            storage:
              resources:
                requests:
                  storage: '${DISK_SIZE}'
      running: false
      template:
        spec:
          domain:
            cpu:
              cores: ${{CPU_CORES}}
            resources:
              requests:
                memory: '${MEMORY}'
            devices:
              disks:
                - disk:
                    bus: virtio
                  name: rootdisk
          volumes:
            - dataVolume:
                name: '${NAME}-root'
              name: rootdisk
parameters:
  - name: NAME
    generate: expression
    from: 'rhel9-[a-z0-9]{8}'
  - name: CPU_CORES
    value: '2'
  - name: MEMORY
    value: '4Gi'
  - name: DISK_SIZE
    value: '30Gi'
```

## Deploy VM from Template

```bash
oc process rhel9-server -p NAME=my-new-vm -p CPU_CORES=4 -p MEMORY=8Gi | oc apply -f -
```
