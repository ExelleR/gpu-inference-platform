SHELL := /bin/bash
# Honoured by GNU Make >= 3.82; macOS ships 3.81, so pipeline recipes also set pipefail explicitly.
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := all

TOOLS_DIR      := .tools/bin
SCHEMAS_DIR    := .tools/schemas
BUILD_DIR      := build
KUBECONFORM_VERSION := 0.8.0
K8S_SCHEMA_VERSION  := 1.35.0
UNAME_S := $(shell uname -s | tr '[:upper:]' '[:lower:]')
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_M),x86_64)
  ARCH := amd64
else
  ARCH := arm64
endif
export PATH := $(CURDIR)/$(TOOLS_DIR):$(PATH)

TF_STAGES := infra/terraform/bootstrap infra/terraform/gke
CHARTS    := platform/argocd/bootstrap-chart platform/argocd/apps platform/serving/vllm-chart
VLLM_CHART := platform/serving/vllm-chart
# release:values-file pairs rendered from the vLLM chart; the release names match the real deployments.
VLLM_RELEASES := vllm-baseline:values-baseline-l4 vllm-raw-v024:values-raw-v024 \
  vllm-single:values-timeslice-single vllm-shared:values-timeslice-shared
STATIC_MANIFEST_DIRS := platform/gpu platform/monitoring platform/serving/kserve
KUBECONFORM_ARGS := -strict -summary -kubernetes-version $(K8S_SCHEMA_VERSION) \
  -schema-location default \
  -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  -schema-location '$(SCHEMAS_DIR)/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  -ignore-missing-schemas

.PHONY: tools
tools: $(TOOLS_DIR)/kubeconform
	uv sync --project bench

$(TOOLS_DIR)/kubeconform:
	mkdir -p "$(TOOLS_DIR)"
	set -o pipefail; curl -fsSL https://github.com/yannh/kubeconform/releases/download/v$(KUBECONFORM_VERSION)/kubeconform-$(UNAME_S)-$(ARCH).tar.gz \
	  | tar -xz -C "$(TOOLS_DIR)" kubeconform

.PHONY: lint
lint:
	terraform fmt -check -recursive infra
	uv run --project bench ruff check bench scripts
	uv run --project bench ruff format --check bench scripts

.PHONY: tf-validate
tf-validate:
	@for stage in $(TF_STAGES); do \
	  echo "== $$stage"; \
	  terraform -chdir=$$stage init -backend=false -input=false >/dev/null && \
	  terraform -chdir=$$stage validate || exit 1; \
	done

.PHONY: helm-lint
helm-lint:
	mkdir -p "$(BUILD_DIR)/charts"
	@for chart in $(CHARTS); do \
	  echo "== $$chart"; \
	  helm lint $$chart || exit 1; \
	  helm template test $$chart --set repo.url=https://example.invalid/repo.git \
	    > "$(BUILD_DIR)/charts/$$(basename $$chart).yaml" || exit 1; \
	done
	helm template platform-apps-local platform/argocd/apps --set repo.url=https://example.invalid/repo.git \
	  --set serving.enabled=false --set monitoring.enabled=false > "$(BUILD_DIR)/charts/platform-apps-local.yaml"
	@for pair in $(VLLM_RELEASES); do \
	  release=$${pair%%:*}; values=$(VLLM_CHART)/$${pair#*:}.yaml; \
	  echo "== $(VLLM_CHART) $$release -f $$values"; \
	  helm lint $(VLLM_CHART) -f $$values || exit 1; \
	  helm template $$release $(VLLM_CHART) -f $$values \
	    > "$(BUILD_DIR)/charts/vllm-chart-$$release.yaml" || exit 1; \
	done

.PHONY: kubeconform
kubeconform: helm-lint
	kubeconform $(KUBECONFORM_ARGS) $(STATIC_MANIFEST_DIRS) "$(BUILD_DIR)/charts"

.PHONY: test
test:
	uv run --project bench pytest -q bench/tests

.PHONY: render-check
render-check:
	rm -rf "$(BUILD_DIR)/render" && mkdir -p "$(BUILD_DIR)/render"
	uv run --project bench gpubench validate bench/experiments/*.yaml
	uv run --project bench gpubench render bench/experiments/*.yaml -o "$(BUILD_DIR)/render"
	kubeconform $(KUBECONFORM_ARGS) "$(BUILD_DIR)/render"

.PHONY: schemas
schemas:
	mkdir -p "$(SCHEMAS_DIR)"
	set -o pipefail; helm template kserve-crd oci://ghcr.io/kserve/charts/kserve-crd --version v0.20.0 --include-crds \
	  | uv run --project bench python scripts/openapi2jsonschema.py "$(SCHEMAS_DIR)"
	set -o pipefail; helm template keda keda --repo https://kedacore.github.io/charts --version 2.20.2 --include-crds \
	  | uv run --project bench python scripts/openapi2jsonschema.py "$(SCHEMAS_DIR)"
	set -o pipefail; curl -fsSL https://raw.githubusercontent.com/GoogleCloudPlatform/prometheus-engine/main/manifests/setup.yaml \
	  | uv run --project bench python scripts/openapi2jsonschema.py "$(SCHEMAS_DIR)"

.PHONY: all
all: lint tf-validate helm-lint kubeconform test render-check

# ---- Cloud targets (user-run; need gcloud auth) ----
BOOTSTRAP := infra/terraform/bootstrap
GKE       := infra/terraform/gke
# make up SERVING=true deploys the serving tier (baseline vLLM + KServe InferenceService).
SERVING   ?= false
STATE_BUCKET = $(shell terraform -chdir=$(BOOTSTRAP) output -raw state_bucket)
PROJECT_ID   = $(shell terraform -chdir=$(BOOTSTRAP) output -raw project_id)

.PHONY: bootstrap
bootstrap:
	terraform -chdir=$(BOOTSTRAP) init -input=false
	terraform -chdir=$(BOOTSTRAP) apply -input=false

.PHONY: up
up:
	terraform -chdir=$(GKE) init -input=false -backend-config="bucket=$(STATE_BUCKET)"
	terraform -chdir=$(GKE) apply -input=false -var="project_id=$(PROJECT_ID)" -var="serving_enabled=$(SERVING)"
	@terraform -chdir=$(GKE) output -raw get_credentials
	@echo

.PHONY: down
down:
	terraform -chdir=$(GKE) destroy -input=false -var="project_id=$(PROJECT_ID)" -var="serving_enabled=$(SERVING)"

.PHONY: argocd-ui
argocd-ui:
	@echo "admin password:"; kubectl --context "$(KUBE_CONTEXT)" -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d || true; echo
	kubectl --context "$(KUBE_CONTEXT)" -n argocd port-forward svc/argocd-server 8080:80

.PHONY: gpu-smoke
gpu-smoke:
	kubectl delete -f platform/gpu/manual/gpu-smoke-job.yaml --ignore-not-found
	kubectl apply -f platform/gpu/manual/gpu-smoke-job.yaml
	kubectl -n gpu-system wait --for=condition=complete job/gpu-smoke --timeout=15m
	kubectl -n gpu-system logs job/gpu-smoke

# ---- Local GitOps mode (Docker Desktop Kubernetes; no GPUs, no Terraform) ----
GIT_REPO_URL   ?= $(shell git remote get-url origin 2>/dev/null)
GIT_REVISION   ?= $(shell git rev-parse --abbrev-ref HEAD 2>/dev/null)
GIT_REPO_TOKEN ?=
LOCAL_SET = --set repo.url=$(GIT_REPO_URL) --set repo.revision=$(GIT_REVISION) --set serving.enabled=false --set monitoring.enabled=false
local-up local-wait local-status local-down: KUBE_CONTEXT ?= docker-desktop

.PHONY: local-up
local-up:
	@kubectl --context "$(KUBE_CONTEXT)" cluster-info >/dev/null 2>&1 || { echo "kube context $(KUBE_CONTEXT) is not reachable: enable Kubernetes in Docker Desktop (Settings > Kubernetes) and retry"; exit 1; }
	helm repo add argo https://argoproj.github.io/argo-helm --force-update
	helm --kube-context "$(KUBE_CONTEXT)" upgrade --install argocd argo/argo-cd --version 10.6.0 \
	  -n argocd --create-namespace -f platform/argocd/argocd-values.yaml --wait --timeout 600s
	helm --kube-context "$(KUBE_CONTEXT)" upgrade --install argocd-bootstrap platform/argocd/bootstrap-chart \
	  -n argocd $(LOCAL_SET) --set-string repo.token="$$GIT_REPO_TOKEN"
	@echo "Argo CD is syncing $(GIT_REPO_URL)@$(GIT_REVISION); run: make local-wait"

.PHONY: local-wait
local-wait:
	@set -o pipefail; want=$$(( $$(helm template t platform/argocd/apps $(LOCAL_SET) | grep -c '^kind: Application') + 1 )); \
	end=$$((SECONDS+900)); echo "waiting for $$want Applications (15m timeout)"; \
	while :; do \
	  json=$$(kubectl --context "$(KUBE_CONTEXT)" -n argocd get applications.argoproj.io -o json 2>/dev/null) || json='{"items":[]}'; \
	  have=$$(printf '%s' "$$json" | jq '.items|length'); \
	  bad=$$(printf '%s' "$$json" | jq -r '.items[]|select(.status.sync.status!="Synced" or .status.health.status!="Healthy")|.metadata.name'); \
	  if [ "$$have" -ge "$$want" ] && [ -z "$$bad" ]; then echo "ready: $$have/$$want Applications Synced and Healthy"; exit 0; fi; \
	  if [ $$SECONDS -ge $$end ]; then echo "timeout; not ready: $$bad (a private repo needs GIT_REPO_TOKEN)"; exit 1; fi; \
	  sleep 10; \
	done

.PHONY: local-status
local-status:
	kubectl --context "$(KUBE_CONTEXT)" -n argocd get applications.argoproj.io -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'
	kubectl --context "$(KUBE_CONTEXT)" get pods -A

.PHONY: local-down
local-down:
	helm --kube-context "$(KUBE_CONTEXT)" uninstall argocd-bootstrap -n argocd --cascade foreground --wait --timeout 600s --ignore-not-found
	helm --kube-context "$(KUBE_CONTEXT)" uninstall argocd -n argocd --wait --timeout 300s --ignore-not-found
	kubectl --context "$(KUBE_CONTEXT)" delete namespace argocd cert-manager keda kserve gpu-system inference bench --ignore-not-found
