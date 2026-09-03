# cluster-hjbrk prerequisites

These manifests must be applied **once** to the MTV/OCP Virt target cluster
(`https://api.cluster-hjbrk.dyn.redhatworkshops.io:6443`) before the agent
can run successfully. They are NOT managed by ArgoCD (which only targets the
qn6c5 cluster).

## Apply

```bash
oc login https://api.cluster-hjbrk.dyn.redhatworkshops.io:6443 \
  --username=admin --password=<password> --insecure-skip-tls-verify=true

oc apply -f deploy/cluster-hjbrk/
```

## Why

`forklift-cluster-reader-rbac.yaml` — The agent token is the
`forklift-controller` service account in `openshift-mtv`. The
`check_cluster_readiness` tool calls `core.list_node()`, which requires
cluster-scoped `list nodes` access. Without `cluster-reader`, every
pre-flight check returns `ERROR / NOT READY` for worker nodes, blocking the
Coordinator from ever routing to the migration pipeline.
