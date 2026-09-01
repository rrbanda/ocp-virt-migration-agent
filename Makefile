# ocp-virt-migration-agent — Developer Workflow
#
# Usage:
#   make init              — Copy .env.example to .env
#   make env               — Create venv and install deps
#   make run               — Start ADK api_server locally
#   make run-api           — Start OpenAI-compatible FastAPI server
#   make test              — Run unit tests
#   make test-behavioral   — Run behavioral tests
#   make lint              — Run ruff linter
#   make scan              — Run gitleaks on staged changes
#   make build             — Build container image
#   make push              — Push image to registry
#   make deploy-helm       — Deploy via Helm (manual)
#   make deploy-argocd     — Deploy via ArgoCD (GitOps)
#   make seal-secrets      — Seal secrets with kubeseal

SHELL := /bin/bash
.DEFAULT_GOAL := help

-include .env
export

AGENT_NAME ?= ocp-virt-migration-agent
CONTAINER_IMAGE ?= ghcr.io/rrbanda/ocp-virt-migration-agent
NAMESPACE ?= ocp-virt-agent
MIGRATION_AGENT_URL ?= http://localhost:8080
CONTAINER_CLI := $(shell command -v podman 2>/dev/null || command -v docker 2>/dev/null)

.PHONY: help init env run run-api test test-behavioral lint format eval-schema scan scan-all \
        build push deploy-helm undeploy-helm deploy-argocd undeploy-argocd seal-secrets dry-run \
        build-openshell push-openshell deploy-openshell undeploy-openshell clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------
init: ## Copy .env.example to .env
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env — edit it with your configuration"; \
	else \
		echo ".env already exists"; \
	fi

env: ## Create venv and install dependencies
	uv sync --dev
	@echo "Environment ready. Activate with: source .venv/bin/activate"

run: ## Start ADK api_server on port 8000
	uv run adk api_server --host 0.0.0.0 --port 8000 --allow_origins '*' .

run-api: ## Start OpenAI-compatible FastAPI server on port 8080
	uv run uvicorn app.api:fastapi_app --host 0.0.0.0 --port 8080

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------
test: ## Run unit tests
	uv run pytest tests/unit/ -v

test-behavioral: ## Run behavioral tests (set MIGRATION_AGENT_URL)
	MIGRATION_AGENT_URL=$(MIGRATION_AGENT_URL) uv run pytest tests/behavioral/ -v

lint: ## Run ruff linter
	uv run ruff check .

format: ## Run ruff formatter
	uv run ruff format .

eval-schema: ## Validate eval dataset schemas
	uv run pytest tests/eval/ -v

scan: ## Run gitleaks on staged changes
	@if command -v rh-gitleaks >/dev/null 2>&1; then \
		rh-gitleaks --staged --verbose; \
	else \
		echo "rh-gitleaks not installed. See deploy/sealed-secrets/README.md"; \
	fi

scan-all: ## Run gitleaks on entire repo history
	@if command -v rh-gitleaks >/dev/null 2>&1; then \
		rh-gitleaks --verbose; \
	else \
		echo "rh-gitleaks not installed."; \
	fi

# ---------------------------------------------------------------------------
# Container Images
# ---------------------------------------------------------------------------
build: ## Build agent container image
	$(CONTAINER_CLI) build --platform linux/amd64 -f deploy/Dockerfile.agent \
		-t $(CONTAINER_IMAGE):latest .

push: ## Push agent image to registry
	$(CONTAINER_CLI) push $(CONTAINER_IMAGE):latest

build-openshell: ## Build OpenShell sandbox image
	$(CONTAINER_CLI) build --platform linux/amd64 -f deploy/Containerfile.openshell \
		-t $(CONTAINER_IMAGE)-sandbox:latest .

push-openshell: ## Push sandbox image to registry
	$(CONTAINER_CLI) push $(CONTAINER_IMAGE)-sandbox:latest

# ---------------------------------------------------------------------------
# Deployment: Helm (manual)
# ---------------------------------------------------------------------------
dry-run: ## Render Helm chart without deploying
	helm template $(AGENT_NAME) deploy/chart \
		-f deploy/values-agent.yaml \
		--namespace $(NAMESPACE)

deploy-helm: ## Deploy to OpenShift via Helm
	@trap 'rm -f .helm-secrets.yaml' EXIT; \
	umask 077; \
	{ printf 'secrets:\n'; \
	  [ -z "$${OPENAI_API_KEY}" ] || printf '  openaiApiKey: "%s"\n' "$${OPENAI_API_KEY}"; \
	  [ -z "$${MTV_API_TOKEN}" ]  || printf '  mtvApiToken: "%s"\n' "$${MTV_API_TOKEN}"; \
	  [ -z "$${VIRT_API_TOKEN}" ] || printf '  virtApiToken: "%s"\n' "$${VIRT_API_TOKEN}"; \
	  [ -z "$${AAP_TOKEN}" ]      || printf '  aapToken: "%s"\n' "$${AAP_TOKEN}"; \
	} > .helm-secrets.yaml; \
	helm upgrade --install $(AGENT_NAME) deploy/chart \
		-f deploy/values-agent.yaml \
		-f .helm-secrets.yaml \
		--namespace $(NAMESPACE) --create-namespace; \
	echo ""; \
	echo "Waiting for rollout..."; \
	oc rollout status deployment/$(AGENT_NAME) -n $(NAMESPACE) --timeout=120s || true; \
	ROUTE=$$(oc get route $(AGENT_NAME) -n $(NAMESPACE) -o jsonpath='{.spec.host}' 2>/dev/null); \
	[ -n "$$ROUTE" ] && echo "Agent available at: https://$$ROUTE"

undeploy-helm: ## Remove Helm deployment
	helm uninstall $(AGENT_NAME) --namespace $(NAMESPACE) || true

# ---------------------------------------------------------------------------
# Deployment: ArgoCD (GitOps)
# ---------------------------------------------------------------------------
deploy-argocd: ## Deploy via ArgoCD (apply Application CRs)
	oc apply -f deploy/argocd/namespace.yaml
	oc apply -f deploy/argocd/application-agent.yaml
	@echo "ArgoCD Application created. Sync will begin automatically."
	@echo "Monitor: oc get application ocp-virt-migration-agent -n openshift-gitops"

undeploy-argocd: ## Remove ArgoCD Application
	oc delete -f deploy/argocd/application-agent.yaml --ignore-not-found

# ---------------------------------------------------------------------------
# Secrets Management
# ---------------------------------------------------------------------------
seal-secrets: ## Seal secrets with kubeseal (requires /tmp/agent-secrets.yaml)
	@if ! command -v kubeseal >/dev/null 2>&1; then \
		echo "ERROR: kubeseal not installed. Run: brew install kubeseal"; \
		exit 1; \
	fi
	@if [ ! -f /tmp/agent-secrets.yaml ]; then \
		echo "ERROR: /tmp/agent-secrets.yaml not found."; \
		echo "Create it first -- see deploy/sealed-secrets/README.md"; \
		exit 1; \
	fi
	kubeseal --format yaml \
		--controller-name=sealed-secrets-controller \
		--controller-namespace=kube-system \
		< /tmp/agent-secrets.yaml \
		> deploy/sealed-secrets/agent-secrets.yaml
	@echo "Sealed secret written to deploy/sealed-secrets/agent-secrets.yaml"
	@echo "Safe to commit. Run: rm /tmp/agent-secrets.yaml"

# ---------------------------------------------------------------------------
# OpenShell sandbox
# ---------------------------------------------------------------------------
deploy-openshell: ## Create OpenShell sandbox
	openshell sandbox create \
		--name $(AGENT_NAME) \
		--from $(CONTAINER_IMAGE)-sandbox:latest \
		--forward 8080 \
		-e ADK_MODEL=$${ADK_MODEL:-openai/meta-llama/Llama-3.1-70B-Instruct} \
		-e OPENAI_API_BASE=$${OPENAI_API_BASE:-http://localhost:8321/v1} \
		-e OPENAI_API_KEY=$${OPENAI_API_KEY:-not-needed} \
		-e AGENT_MODE=pipeline \
		-e SKILLS_DIR=/skills \
		-e MIGRATION_DRY_RUN=$${MIGRATION_DRY_RUN:-true} \
		-- uvicorn app.api:fastapi_app --host 0.0.0.0 --port 8080

undeploy-openshell: ## Delete OpenShell sandbox
	openshell sandbox delete $(AGENT_NAME)

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
clean: ## Remove venv and caches
	rm -rf .venv __pycache__ .pytest_cache .helm-secrets.yaml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
