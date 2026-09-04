# GPU Quota Request

A fresh GCP project has no GPU quota. Request it before the first `make up` with a GPU pool
enabled — this is a manual Console step; Terraform cannot do it for you.

## 1. Upgrade billing first

Upgrade the billing account from the free trial before requesting quota. Trial accounts are not
eligible for GPU quota increases.

## 2. Where to request

Console: **IAM & Admin → Quotas & System Limits**.

## 3. What to request

Request all of the following in one submission. The `l4-spot` pool scales to three nodes: two for
the opt-in serving tier (`make up SERVING=true` — the baseline vLLM Deployment and the KServe
predictor hold one L4 each) plus one for a benchmark Job, so all three L4-related quotas need to
be 3.

| Quota metric | Value | Scope |
| --- | --- | --- |
| `GPUS_ALL_REGIONS` | 3 | global |
| `NVIDIA_L4_GPUS` | 3 | `us-central1` |
| `PREEMPTIBLE_NVIDIA_L4_GPUS` | 3 | `us-central1` |

Optional — only needed if you plan to enable an A100 pool (`a100-spot` for `08-a100-vs-l4`, or
`a100-mig`; see `infra/terraform/gke/README.md`):

| Quota metric | Value | Scope |
| --- | --- | --- |
| `NVIDIA_A100_GPUS` | 1 | `us-central1` |
| `PREEMPTIBLE_NVIDIA_A100_GPUS` | 1 | `us-central1` |

`infra/terraform/gke/variables.tf` defaults `region` to `us-central1` and `zone` to
`us-central1-a`; request quota in that region unless you've overridden those variables in
`terraform.tfvars`.

## 4. Justification text

```
LLM inference benchmarking on GKE with up to three spot L4 GPUs (two serving replicas plus one benchmark Job), hobby project, hourly usage, budget alert configured
```

## 5. Turnaround

Minutes, if the billing account already has payment history. Up to a week otherwise.

## 6. Failure symptom if you skip this

`terraform apply` succeeds regardless — `make up` only creates the node pool / autoscaler
configuration, not the VM itself. The failure shows up later, when the autoscaler tries to scale a
GPU pool up from zero:

```bash
kubectl describe pod <pending-pod> -n <namespace>
```

Look for a `GCE_QUOTA_EXCEEDED` scale-up error in the pod's events — not a Terraform error.

## 7. Check current quota

The L4 and A100 quotas are regional; `GPUS_ALL_REGIONS` is a project-wide quota that only
`project-info` reports:

```bash
gcloud compute regions describe us-central1 --project <project_id> --format="yaml(quotas)" | grep -A2 -E "L4|A100"
gcloud compute project-info describe --project <project_id> --format="yaml(quotas)" | grep -A2 GPUS_ALL_REGIONS
```

## Next

`docs/runbooks/bring-up.md`.
