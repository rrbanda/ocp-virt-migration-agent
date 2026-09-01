# Operator Readiness Checklist

## OpenShift Virtualization

```bash
oc get csv -n openshift-cnv | grep virtualization
# Status must be: Succeeded

oc get hyperconverged kubevirt-hyperconverged -n openshift-cnv -o jsonpath='{.status.conditions[?(@.type=="Available")].status}'
# Must return: True
```

Verify live migration network is configured:
```bash
oc get hyperconverged kubevirt-hyperconverged -n openshift-cnv -o jsonpath='{.spec.liveMigrationConfig.network}'
```

## Migration Toolkit for Virtualization (MTV)

```bash
oc get csv -n openshift-mtv | grep forklift
# Status must be: Succeeded

oc get forkliftcontroller -n openshift-mtv
# Must exist and be Ready
```

Verify providers:
```bash
oc get providers -n <mtv-namespace>
# Should show at least: host (OpenShift) + one VMware/vsphere provider
```

## OpenShift Data Foundation (if used)

```bash
oc get csv -n openshift-storage | grep odf
# Status must be: Succeeded

oc get storagecluster -n openshift-storage
# Phase must be: Ready
```

## NMState Operator

```bash
oc get csv -A | grep nmstate
# Required for post-install bond/bridge/VLAN configuration

oc get nmstate
# Must exist (created after operator install)
```

## SR-IOV Operator (if needed)

```bash
oc get csv -n openshift-sriov-network-operator | grep sriov
# Only required for VMs needing hardware passthrough

oc get sriovnetworknodestate -n openshift-sriov-network-operator
# Shows VF status per node
```
