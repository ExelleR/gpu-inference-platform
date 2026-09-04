# L4 spot as the default GPU pool, A100 (spot or MIG) as opt-in

Status: accepted
Date: 2026-09-01

## Context

`infra/terraform/gke/variables.tf` defines four GPU node pools: `l4-spot` (enabled by default, up to three nodes), `l4-timeslice` (disabled), `a100-spot` (disabled) and `a100-mig` (disabled). All default to Spot VMs and scale from zero. Which pool runs by default is a cost/capability trade-off between NVIDIA L4 (Ada Lovelace, `g2-standard-4`) and A100 40GB (Ampere, `a2-highgpu-1g`).

## Decision

`l4-spot` is enabled by default; `a100-spot` (a whole spot A100-40GB, the pool `08-a100-vs-l4` pins through `node_selector: {pool: a100-spot}`), `a100-mig` (MIG profile `3g.20gb`) and `l4-timeslice` are opt-in overrides in `terraform.tfvars`. L4 spot runs about $0.424/hour, roughly 118 hours per $50 of budget; A100-40GB spot runs about $2.12/hour, roughly 23 hours per $50 — nearly five times the burn rate for the same money. L4 (Ada) has no MIG capability on GKE at all; its only sharing mechanism is GPU time-slicing (`TIME_SHARING`), which is why `l4-timeslice` sets `sharing` rather than `partition_size`. A100 supports MIG, and `3g.20gb` (20 GB) is the default partition because the smallest profile, `1g.5gb` (5 GB), cannot hold an FP8 Qwen3-8B checkpoint plus its KV cache; `1g.5gb` is reserved for the tiny Qwen3-0.6B smoke-test model instead. Enabling either Spot GPU pool draws against the project's `PREEMPTIBLE_*`-prefixed GPU quota metrics rather than the on-demand family, so a fresh GCP project typically needs a quota increase request before the first `make up` with GPUs enabled. `bench/prices.yaml` carries no separate row for `l4-timeslice`: it is billed as the same `g2-standard-4` Spot VM as `l4-spot`, so experiments that target it key their cost model on the `l4-spot` price.

## Consequences

Defaulting to L4 keeps a full work session affordable and makes A100 a deliberate, opt-in cost decision rather than an accidental one. The MIG-vs-time-slicing split also means the two sharing experiments measure different things: L4 time-slicing tests scheduler/throughput sharing only, while A100 MIG additionally tests hardware-partitioned memory isolation. Because A100 is opt-in and quota-gated, enabling it for the first time may add a quota-approval wait to bring-up.
