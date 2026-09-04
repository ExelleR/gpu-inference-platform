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
	@echo "admin password:"; kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d || true; echo
	kubectl -n argocd port-forward svc/argocd-server 8080:80

.PHONY: gpu-smoke
gpu-smoke:
	kubectl apply -f platform/gpu/manual/gpu-smoke-job.yaml
	kubectl -n gpu-system wait --for=condition=complete job/gpu-smoke --timeout=15m
	kubectl -n gpu-system logs job/gpu-smoke
