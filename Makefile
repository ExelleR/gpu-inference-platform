SHELL := /bin/bash
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
	curl -fsSL https://github.com/yannh/kubeconform/releases/download/v$(KUBECONFORM_VERSION)/kubeconform-$(UNAME_S)-$(ARCH).tar.gz \
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
	helm template baseline platform/serving/vllm-chart -f platform/serving/vllm-chart/values-baseline-l4.yaml \
	  > "$(BUILD_DIR)/charts/vllm-chart-baseline.yaml"

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
	helm show crds oci://ghcr.io/kserve/charts/kserve-crd --version v0.20.0 \
	  | uv run --project bench python scripts/openapi2jsonschema.py "$(SCHEMAS_DIR)"
	curl -fsSL https://raw.githubusercontent.com/GoogleCloudPlatform/prometheus-engine/main/manifests/setup.yaml \
	  | uv run --project bench python scripts/openapi2jsonschema.py "$(SCHEMAS_DIR)"
	helm show crds keda --repo https://kedacore.github.io/charts --version 2.20.2 \
	  | uv run --project bench python scripts/openapi2jsonschema.py "$(SCHEMAS_DIR)"

.PHONY: all
all: lint tf-validate helm-lint kubeconform test render-check

# ---- Cloud targets (user-run; need gcloud auth) ----
BOOTSTRAP := infra/terraform/bootstrap
GKE       := infra/terraform/gke
STATE_BUCKET = $(shell terraform -chdir=$(BOOTSTRAP) output -raw state_bucket)
PROJECT_ID   = $(shell terraform -chdir=$(BOOTSTRAP) output -raw project_id)

.PHONY: bootstrap
bootstrap:
	terraform -chdir=$(BOOTSTRAP) init -input=false
	terraform -chdir=$(BOOTSTRAP) apply -input=false

.PHONY: up
up:
	terraform -chdir=$(GKE) init -input=false -backend-config="bucket=$(STATE_BUCKET)"
	terraform -chdir=$(GKE) apply -input=false -var="project_id=$(PROJECT_ID)"
	@terraform -chdir=$(GKE) output -raw get_credentials
	@echo

.PHONY: down
down:
	terraform -chdir=$(GKE) destroy -input=false -var="project_id=$(PROJECT_ID)"

.PHONY: argocd-ui
argocd-ui:
	@echo "admin password:"; kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
	kubectl -n argocd port-forward svc/argocd-server 8080:80

.PHONY: gpu-smoke
gpu-smoke:
	kubectl apply -f platform/gpu/manual/gpu-smoke-job.yaml
	kubectl -n gpu-system wait --for=condition=complete job/gpu-smoke --timeout=15m
	kubectl -n gpu-system logs job/gpu-smoke
