# KServe v0.20.0 in Standard mode, no ingress, KEDA installed but unwired

Status: accepted
Date: 2026-09-01

## Context

KServe v0.20.0 offers three deployment modes: Serverless (Knative), ModelMesh, and Standard — renamed from RawDeployment in recent releases, a plain Kubernetes Deployment/Service without a Knative wrapper. `platform/kserve/values.yaml` sets `deploymentMode: Standard` at the controller level, and `platform/serving/kserve/inferenceservice.yaml` repeats it via the `serving.kserve.io/deploymentMode: Standard` annotation. The `InferenceService` uses the `huggingface` `modelFormat`, which KServe backs with a vLLM-based serving runtime, to serve `Qwen/Qwen3-8B-FP8` on an L4 node. KEDA is deployed by the same app-of-apps chart (`platform/keda`), but nothing yet creates a `ScaledObject` against the predictor.

## Decision

Run KServe in Standard mode with ingress creation disabled (`disableIngressCreation: true`, `enableGatewayApi: false`): the predictor is reached in-cluster only, matching the raw vLLM Deployment's `ClusterIP` Service, with no external load balancer or Gateway API route yet. Standard is KServe's own recommendation for LLM workloads — Knative's request-based autoscaling and queue-proxy don't suit long-lived, streaming LLM connections — and, as of v0.20.0, the only deployment mode KEDA can attach to, which is why KEDA is installed now even though no `ScaledObject` wires it to the predictor yet. The Hugging Face runtime is vLLM-backed but bundles vLLM 0.24.0, older than the raw path's pinned `v0.28.0`; to keep experiment 07 (`bench/experiments/07-kserve-vs-raw.yaml`, KServe vs. raw) an apples-to-apples engine comparison, its raw-path target is deployed pinned to vLLM `v0.24.0` instead of the repo's usual `v0.28.0`.

## Consequences

Isolating KServe's overhead from engine-version drift required a one-off vLLM pin for experiment 07 only; the baseline Deployment and every other experiment stay on `v0.28.0`. With no ingress, the `InferenceService` is unreachable from outside the cluster — fine for benchmarking, not for serving real traffic. `LLMInferenceService` (the newer `serving.kserve.io/v1alpha1` API built on llm-d) and an Envoy Gateway-based ingress are follow-up work once Standard-mode KEDA autoscaling is wired up. `platform/monitoring/clusterpodmonitoring.yaml` scrapes the predictor's metrics on port 8080, a value taken from KServe's defaults and not yet verified against a running pod; it is checked at first run.

## Update 2026-09-05: KEDA wired to queue depth

The `InferenceService` now carries `serving.kserve.io/autoscalerClass: keda`, `maxReplicas: 2` and an
`autoScaling` External metric: KServe generates a KEDA `ScaledObject` that queries
`sum(vllm:num_requests_waiting{namespace="inference"})` through the Managed Prometheus frontend
(ADR 0008) and adds a replica when more than four requests are queued. Without
`OBSERVABILITY=true` the metric is unavailable and KEDA holds `minReplicas`; the annotation can be
removed on a live cluster to fall back to a fixed replica count. Experiment
`09-kserve-autoscale` exercises it; the cost note is in `docs/runbooks/cost-control.md`.
