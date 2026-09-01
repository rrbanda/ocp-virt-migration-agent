# SealedSecrets for OCP Virt Migration Agent

SealedSecrets encrypts Kubernetes Secrets so they can be safely stored in git.
Only the SealedSecrets controller on the target cluster can decrypt them.

## Prerequisites

1. SealedSecrets controller installed on the cluster:
   ```bash
   oc apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.3/controller.yaml
   ```

2. `kubeseal` CLI installed locally:
   ```bash
   brew install kubeseal        # macOS
   # or download from https://github.com/bitnami-labs/sealed-secrets/releases
   ```

## Creating Sealed Secrets

### Step 1: Create a plaintext Secret (DO NOT commit this)

```bash
cat > /tmp/agent-secrets.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: ocp-virt-migration-agent-secret
  namespace: ocp-virt-agent
type: Opaque
stringData:
  openai-api-key: "YOUR_API_KEY_HERE"
  mtv-api-token: "YOUR_MTV_TOKEN_HERE"
  virt-api-token: "YOUR_VIRT_TOKEN_HERE"
  aap-token: "YOUR_AAP_TOKEN_HERE"
  mlflow-tracking-token: "YOUR_MLFLOW_TOKEN_HERE"
EOF
```

### Step 2: Fetch the cluster's public cert

```bash
kubeseal --fetch-cert \
  --controller-name=sealed-secrets-controller \
  --controller-namespace=kube-system \
  > /tmp/sealed-secrets-cert.pem
```

### Step 3: Seal the secret

```bash
kubeseal --format yaml \
  --cert /tmp/sealed-secrets-cert.pem \
  < /tmp/agent-secrets.yaml \
  > deploy/sealed-secrets/agent-secrets.yaml
```

### Step 4: Clean up plaintext and commit the sealed version

```bash
rm /tmp/agent-secrets.yaml /tmp/sealed-secrets-cert.pem
git add deploy/sealed-secrets/agent-secrets.yaml
git commit -m "chore: update sealed secrets for agent deployment"
```

### Step 5: Apply to cluster (ArgoCD does this automatically)

```bash
oc apply -f deploy/sealed-secrets/agent-secrets.yaml
```

The SealedSecrets controller decrypts it into a regular Secret named
`ocp-virt-migration-agent-secret` in the `ocp-virt-agent` namespace.

## Rotating Secrets

1. Update values in the plaintext Secret YAML (`/tmp/agent-secrets.yaml`)
2. Re-seal with `kubeseal`
3. Commit the new `agent-secrets.yaml`
4. ArgoCD syncs the update; controller re-decrypts

## Makefile Shortcut

```bash
make seal-secrets    # runs steps 2-3 using /tmp/agent-secrets.yaml
```

## What NOT to Do

- NEVER commit plaintext Secret YAML to git
- NEVER paste cluster credentials or tokens into chat, issues, or PRs
- NEVER use `oc create secret` with tokens visible in shell history (use files)
