# Local GitOps mode on Docker Desktop

Status: accepted
Date: 2026-09-04

## Context

The platform tier under `platform/argocd/apps` was written and verified offline (Helm lint,
kubeconform) but had never been synced by a real Argo CD: the sync waves, the Lua health check for
child Applications, the OCI registry Secret ordering and the KServe chart values were untested.
GPU quota on Google Cloud can take days to arrive and every GKE session costs money. The
development machine runs Docker Desktop with Kubernetes 1.36 on arm64, and Argo CD, cert-manager,
KEDA and the KServe controller all publish arm64 images. The only GKE-specific object in the tier
is the Managed Prometheus scrape configuration, whose `monitoring.googleapis.com` CRD does not
exist elsewhere.

## Decision

Add a Helm-driven local mode: `make local-up` installs the same Argo CD chart version with the
same values file and the same bootstrap chart as the Terraform stage, against the `docker-desktop`
kube context, with `serving.enabled=false` and a new `monitoring.enabled=false` toggle. The toggle
mirrors `serving.enabled` through the bootstrap chart's Helm parameters and defaults to `true`, so
GKE behaviour is unchanged and Terraform is not modified. `make local-wait`, `make local-status`
and `make local-down` complete the loop; teardown relies on the root Application's finalizer with
Helm's foreground cascade so the child Applications are removed before Argo CD itself.

Installing the Managed Prometheus CRDs standalone (the `prometheus-engine` setup manifest is
CRD-only) was rejected: the objects would be inert without the GKE collector, so skipping the
Application is more honest.

## Consequences

- The waves, health check, OCI Secret and KServe values are exercised for free before the first
  GKE bring-up; a failure here is a manifest bug, not a cloud one.
- Nothing about GPUs, node pools, scaling or cost is learned locally; the serving tier and the
  benchmark harness stay cloud-only.
- Local mode validates the pushed branch: changes must be pushed before they are seen.
- The `helm-lint` target now also renders the local variant, so `make all` keeps both
  configurations schema-valid.
