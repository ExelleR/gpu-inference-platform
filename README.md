# gpu-inference-platform

GPU inference platform on GKE with a reproducible LLM serving benchmark and cost model.

**Status (2026-09):** skeleton. Infrastructure, GitOps tier and harness are in place and verified offline;
first GPU runs are scheduled for October–November 2026. Headline numbers will appear here once
`results/` contains a completed experiment.

## What this is

- Terraform for a zonal GKE Standard cluster with spot L4 / A100 node pools that scale to zero
- Argo CD app-of-apps delivering cert-manager, KServe (Standard mode), KEDA, GPU config and monitoring
- Two serving paths for the same model: a raw vLLM Deployment and a KServe InferenceService
- `gpubench`: a harness that runs vLLM's own benchmark tooling in-cluster, then computes
  cost per million tokens (peak, blended, utilization-adjusted)
- `docs/writeup.md`: what moved the numbers, what did not, and why

## Layout

| Path | Purpose |
| --- | --- |
| `infra/terraform/bootstrap` | GCP project, APIs, tfstate bucket, budget alert (run once) |
| `infra/terraform/gke` | VPC, NAT, cluster, node pools, Argo CD (run per work session) |
| `platform/` | Argo CD-managed manifests and charts |
| `bench/` | `gpubench` harness, experiment definitions, price table |
| `results/` | committed raw benchmark output and generated summaries |
| `docs/` | writeup, methodology, cost model, ADRs, runbooks |

## Quick start

See `docs/runbooks/tools.md`, then `docs/runbooks/bring-up.md`.
