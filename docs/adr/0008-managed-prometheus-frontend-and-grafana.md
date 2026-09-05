# Managed Prometheus query frontend and Grafana as an opt-in observability tier

Status: accepted
Date: 2026-09-05

## Context

Managed Prometheus scrapes every vLLM server on the cluster, but nothing in the repository showed
those metrics, and the writeup needs server-side evidence (queue depth, KV-cache pressure,
preemptions) to explain client-side latency. KEDA was installed without a Prometheus endpoint to
query, so it could not scale anything. Grafana's own Cloud Monitoring datasource would work for a
person but not for KEDA, which needs a Prometheus-compatible HTTP API inside the cluster.

## Decision

Deploy the Managed Prometheus query frontend (`prometheus-engine/frontend`) as a small in-cluster
Deployment behind `frontend.observability.svc:9090`, authenticated through Workload Identity to a
Google service account with `roles/monitoring.viewer` that Terraform creates only when
`observability_enabled` is true. Grafana (the `grafana-community` chart) reads through that
frontend with a provisioned datasource and loads the vLLM dashboard from a labelled ConfigMap.
Both are Argo CD Applications guarded by `observability.enabled`, off by default, GKE only; the
Docker Desktop local mode keeps them off because the frontend image is GKE-specific. No Grafana
admin password is committed; `make grafana-ui` reads the generated Secret.

## Consequences

- One Prometheus API serves both people (Grafana) and machines (KEDA); the autoscaling decision
  in ADR 0005's update builds on it.
- Each dashboard refresh is a Cloud Monitoring API read; the cost note lives in
  `docs/runbooks/cost-control.md`.
- The dashboard is code (`platform/observability/dashboards/vllm.json`), validated as JSON in
  `make all` and reloaded by the sidecar on change.
- Nothing about GPUs is learned without the serving tier or a benchmark running; the tier is
  usually enabled together with `SERVING=true`.
