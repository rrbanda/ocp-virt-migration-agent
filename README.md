# gadk-rhoai

Deploy Google ADK agents with configurable skills on OpenShift, with optional OIDC authentication and LLM flexibility.

## Architecture

```
Browser --> OIDC (Keycloak) --> ADK Web UI (nginx :8080) --> ADK API Server (:8000) --> LLM
                                     |                              |
                                ConfigMap                     ConfigMap
                            (runtime-config.json)           (SKILL.md files)
```

**Single-pod sidecar pattern:**
- `adk-web` container: nginx serving the Angular UI + proxying `/api/` to localhost:8000
- `adk-api` container: `adk api_server` running the agent with skills from `/skills` mount
- Init container: reconstructs the skill directory tree from ConfigMap keys

**No Google Cloud dependency.** All components are open source (Apache 2.0).

## Pre-Built Images

| Image | Description |
|---|---|
| `quay.io/rbrhssa/adk-web:oidc` | ADK Web UI with OIDC auth support (nginx) |
| `quay.io/rbrhssa/adk-agent:skills` | ADK API Server with dynamic skill loading (Python) |

## Quick Start

```bash
# 1. Create namespace
oc new-project adk-web

# 2. Create image pull secret (if images are private)
oc create secret docker-registry quay-pull-secret \
  --docker-server=quay.io \
  --docker-username=YOUR_QUAY_USER \
  --docker-password=YOUR_QUAY_PASS

# 3. Edit deploy/openshift.yaml -- replace placeholders:
#    KEYCLOAK_HOST, REALM_NAME, CLIENT_ID  (or remove auth for anonymous)
#    LLM_API_BASE                          (your LLM endpoint)
#    ADK_MODEL_NAME                        (model identifier)

# 4. Deploy
oc apply -f deploy/openshift.yaml

# 5. Get the URL
oc get route adk-web -o jsonpath='{.spec.host}'
```

## Configuration Reference

### UI Configuration (ConfigMap: `adk-web-config`)

| Field | Default | Description |
|---|---|---|
| `backendUrl` | `/api` | ADK API server URL (use `/api` for sidecar proxy) |
| `auth.enabled` | `false` | Enable OIDC authentication |
| `auth.authority` | - | OIDC issuer URL (e.g., `https://keycloak.example.com/realms/myrealm`) |
| `auth.clientId` | - | OIDC public client ID |
| `auth.scopes` | `openid profile email` | OIDC scopes |
| `auth.rolesClaim` | `realm_access.roles` | Dot-path to roles array in JWT (Okta: `groups`, Azure AD: `roles`) |

### Agent Configuration (Deployment env vars)

| Env Var | Default | Description |
|---|---|---|
| `OPENAI_API_BASE` | - | LLM API endpoint (Llama Stack, Ollama, vLLM, etc.) |
| `OPENAI_API_KEY` | - | LLM API key (set to `not-needed` if provider handles auth) |
| `ADK_MODEL` | `openai/gemini/models/gemini-2.5-flash` | LiteLlm model string |
| `SKILLS_DIR` | `/skills` | Path to skills directory (mounted from ConfigMap) |
| `AGENT_NAME` | `skills_agent` | Agent name shown in UI |
| `AGENT_DESC` | `An agent powered by configurable skills.` | Agent description |
| `AGENT_INSTRUCTION_FILE` | - | Path to agent system instruction markdown file |
| `AGENT_INSTRUCTION` | (built-in default) | Agent system instruction (env var, used if no file) |

## Skills Guide

Skills are `SKILL.md` files following the [agentskills.io](https://agentskills.io) specification. They are stored in the `adk-skills` ConfigMap and mounted into the agent container.

### ConfigMap Naming Convention

ConfigMap keys map to the directory structure using `--` as a path separator:

```
ConfigMap Key                                  Mounted Path
-----------                                    ------------
seo-checklist--SKILL.md                   -->  /skills/seo-checklist/SKILL.md
blog-writer--SKILL.md                     -->  /skills/blog-writer/SKILL.md
blog-writer--references--style-guide.md   -->  /skills/blog-writer/references/style-guide.md
agent-instruction.md                      -->  /skills/agent-instruction.md
```

### Add a New Skill (No Image Rebuild)

```bash
oc patch configmap adk-skills -n adk-web --type merge -p '{
  "data": {
    "my-new-skill--SKILL.md": "---\nname: my-new-skill\ndescription: Does something useful\n---\n\n# Instructions\n\nStep-by-step instructions here..."
  }
}'
oc rollout restart deployment/adk-web -n adk-web
```

### Edit a Skill

```bash
oc edit configmap adk-skills -n adk-web
# Edit the SKILL.md content, save
oc rollout restart deployment/adk-web -n adk-web
```

### Remove a Skill

```bash
oc patch configmap adk-skills -n adk-web --type json \
  -p '[{"op":"remove","path":"/data/my-new-skill--SKILL.md"}]'
oc rollout restart deployment/adk-web -n adk-web
```

### SKILL.md Format

```markdown
---
name: my-skill-name
description: What this skill does and when to use it (max 1024 chars).
---

# Instructions

Step-by-step instructions the agent follows when this skill is activated.

## Step 1: ...
Use `load_skill_resource` to read `references/detailed-guide.md`.

## Step 2: ...
```

## Authentication

### Anonymous Mode (Default)

Remove the `auth` section from the ConfigMap or set `auth.enabled: false`:

```json
{
  "backendUrl": "/api"
}
```

### OIDC Mode (Keycloak, Okta, Auth0, Azure AD)

```json
{
  "backendUrl": "/api",
  "auth": {
    "enabled": true,
    "authority": "https://keycloak.example.com/realms/myrealm",
    "clientId": "my-client-id"
  }
}
```

**Keycloak client setup:**
1. Create a public client (Client authentication: OFF)
2. Enable Standard flow
3. Set Valid redirect URIs: `https://YOUR_ROUTE_URL/*`
4. Set Web origins: `https://YOUR_ROUTE_URL`

## LLM Providers

Works with any OpenAI-compatible API via LiteLlm:

| Provider | `OPENAI_API_BASE` | `ADK_MODEL` | `OPENAI_API_KEY` |
|---|---|---|---|
| **Llama Stack** | `https://llamastack.example.com/v1` | `openai/gemini/models/gemini-2.5-flash` | `not-needed` |
| **Ollama** | `http://ollama-svc:11434/v1` | `openai/llama3.1` | `not-needed` |
| **vLLM** | `http://vllm-svc:8000/v1` | `openai/mistral-7b` | `not-needed` |
| **OpenAI** | `https://api.openai.com/v1` | `openai/gpt-4o` | Your API key |
| **Gemini Direct** | (not needed) | `gemini-2.5-flash` | Set `GOOGLE_API_KEY` instead |

## Building Images

### Build the UI image

```bash
cd /path/to/adk-web  # The google/adk-web fork with OIDC
podman build --platform linux/amd64 -f deploy/Dockerfile -t adk-web:oidc .
```

### Build the agent image

```bash
cd /path/to/gadk-rhoai
podman build --platform linux/amd64 -f deploy/Dockerfile.agent -t adk-agent:skills .
```

## Included Skills

| Skill | Description |
|---|---|
| `seo-checklist` | SEO optimization checklist for blog posts |
| `blog-writer` | Blog post writing with structure templates and style guide |
| `content-research-writer` | Content research and SEO writing methodology |
| `skill-creator` | Meta-skill that generates new SKILL.md definitions |

## License

Apache License 2.0. See [LICENSE](LICENSE).

Agent code uses [google-adk](https://github.com/google/adk-python) (Apache 2.0).
UI uses [adk-web](https://github.com/google/adk-web) (Apache 2.0).
