# GPU Quota Request

A fresh GCP project has no GPU quota. Request it before the first `make up` with a GPU pool
enabled — this is a manual Console step; Terraform cannot do it for you.

## 1. Upgrade billing first

Upgrade the billing account from the free trial before requesting quota. Trial accounts are not
eligible for GPU quota increases.

## 2. Where to request

Console: **IAM & Admin → Quotas & System Limits**.

## 3. What to request

Request all of the following in one submission:

| Quota metric | Value | Scope |
| --- | --- | --- |
| `GPUS_ALL_REGIONS` | 1 | global |
| `NVIDIA_L4_GPUS` | 1 | `us-central1` |
| `PREEMPTIBLE_NVIDIA_L4_GPUS` | 1 | `us-central1` |

Optional — only needed if you plan to enable the `a100-mig` pool
(see `infra/terraform/gke/README.md`):

| Quota metric | Value | Scope |
| --- | --- | --- |
| `NVIDIA_A100_GPUS` | 1 | `us-central1` |
| `PREEMPTIBLE_NVIDIA_A100_GPUS` | 1 | `us-central1` |

`infra/terraform/gke/variables.tf` defaults `region` to `us-central1` and `zone` to
`us-central1-a`; request quota in that region unless you've overridden those variables in
`terraform.tfvars`.

## 4. Justification text

```
Single-GPU LLM inference benchmarking on GKE (spot L4), hobby project, hourly usage, budget alert configured
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

```bash
gcloud compute regions describe us-central1 --format="yaml(quotas)" | grep -A2 -E "L4|A100|GPUS_ALL"
```

## Next

`docs/runbooks/bring-up.md`.
