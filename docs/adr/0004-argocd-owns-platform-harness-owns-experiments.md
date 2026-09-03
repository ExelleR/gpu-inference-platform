# Argo CD owns the platform; `gpubench` owns benchmark execution

Status: accepted
Date: 2026-09-01

## Context

The app-of-apps chart (`platform/argocd/apps`) declares an Argo CD Application per platform component — cert-manager, KEDA, the KServe CRDs and resources, GPU namespaces/quotas/priority classes, monitoring, the KServe `InferenceService`, and the baseline raw vLLM Deployment — all synced with `prune: true` and `selfHeal: true`. Independently, the `gpubench` harness renders and applies its own Jobs, ConfigMaps, and a results PVC per experiment run (`bench/src/gpubench/render.py`, `collect.py`) with plain `kubectl`. These two ownership models cannot overlap on the same objects: `selfHeal` reverts any imperative change to a resource Argo CD manages, and `batch/v1` Jobs are immutable once created, so a Job cannot be re-run under a `selfHeal: true` Application without Argo CD reverting or fighting every new run.

## Decision

Argo CD owns everything under `platform/`: cluster add-ons, GPU namespace/quota/priority-class scaffolding, and the two long-lived serving paths — the baseline vLLM Deployment and the KServe `InferenceService`, both in `inference`. `gpubench` owns the `bench` namespace's experiment-time objects: the `bench-results` PVC, per-run ConfigMaps, and the Jobs it creates and deletes for each sweep. The one exception on the platform side is the GPU smoke-test Job, kept out of Argo CD and applied manually via `make gpu-smoke` from `platform/gpu/manual/gpu-smoke-job.yaml`, for the same immutable-Job reason. The results PVC is `ReadWriteOnce` on a zonal persistent disk (`standard-rwo`), so only one pod can mount it at a time; `gpubench collect` attaches it sequentially — first to the benchmark Job's own pod while it runs, then, after completion, to a short-lived `bench-reader` pod used only to `kubectl cp` results out.

## Consequences

The ownership boundary is scaffolding vs. runtime, not namespace vs. namespace: Argo CD still declares the `bench` namespace shell itself, and only what happens inside it at experiment time is imperative. The RWO/zonal-PD sequencing means result collection cannot overlap a running Job, capping the harness to one experiment's results at a time. A GCS bucket read and written through Workload Identity is the planned v2 for results storage, which would drop both the RWO sequencing constraint and the manual reader-pod copy step.
