# Cost per million tokens on a single L4: what moved the number

## Summary

No benchmark has run yet; the numbers below arrive after the first runs in November 2026 and will live in [`results/`](../results/) alongside the raw data behind them.

## Setup

Every experiment runs as a Kubernetes Job inside the same GKE Standard zonal cluster (`us-central1-a`); the default pool is a single spot L4 serving `Qwen/Qwen3-8B-FP8` with vLLM `v0.28.0`, with per-experiment deviations covered below and the full harness described in `docs/methodology.md`.

## Baseline

The baseline (`bench/experiments/01-baseline-l4.yaml`) runs `Qwen3-8B-FP8` with `--max-model-len 8192` and `--gpu-memory-utilization 0.92` set explicitly (the memory setting every 8B variant shares) and no other tuning, across four concurrency levels (1, 4, 16, 64), so later experiments change one thing at a time against it.

## Experiments

Each engine experiment changes one variable against the baseline; the two platform experiments (06, 07) instead compare serving paths for the same model. The file linked in each subsection is the authoritative definition.

### Quantization (bf16 / FP8 / AWQ)

`bench/experiments/02-quant-l4.yaml` asks whether quantization changes latency and throughput on L4 by running `Qwen3-8B` as bf16, FP8 and AWQ across the same four concurrency levels as the baseline.

### KV-cache dtype

`bench/experiments/03-kv-fp8.yaml` asks whether forcing an FP8 KV cache (`--kv-cache-dtype fp8`) changes throughput or latency versus vLLM's automatic KV-cache dtype.

### Batching limits

`bench/experiments/04-batching.yaml` sweeps `max-num-seqs` (32/64/128/256) against `max-num-batched-tokens` (1024/2048/4096/8192) to see how vLLM's continuous-batching limits trade off throughput and latency around the L4 defaults (256/2048).

### Prefix caching as a control

`bench/experiments/05-prefix-cache-control.yaml` disables automatic prefix caching as a control arm, to measure how much of the baseline's throughput and latency it actually accounts for.

### Time-slicing one L4

`bench/experiments/06-timeslice.yaml` compares two small `Qwen3-1.7B` replicas time-sliced on one L4 against a single replica, asking whether sharing buys throughput or only lower queueing latency.

### KServe vs raw Deployment

`bench/experiments/07-kserve-vs-raw.yaml` compares a KServe `InferenceService` against a raw Deployment serving the same model to price what the KServe layer itself costs, with the raw side pinned to vLLM `v0.24.0` to match KServe's bundled runtime so the comparison isolates the platform layer rather than engine-version drift (`docs/adr/0005-kserve-standard-mode-no-ingress.md`).

### A100 vs L4

`bench/experiments/08-a100-vs-l4.yaml` reruns FP8 vs bf16 on a spot A100-40GB to ask whether the L4 quantization story holds on Ampere hardware, where the FP8 checkpoint runs as W8A16 via the Marlin kernel instead of native FP8 tensor cores (`docs/adr/0006-model-choice-qwen3.md`).

## What did not help

No experiment has run yet, so nothing can be ruled out here; once results land in [`results/`](../results/), this section will name the changes that cost GPU-hours without moving throughput, latency, or $/M tokens.

## Cost model

The formula, price table and utilization-adjusted views used throughout this writeup are defined once in [`cost-model.md`](cost-model.md).

## Limitations

Every result here is single-GPU and single-node, driven by a replay of recorded ShareGPT conversations rather than production traffic, subject to spot-VM performance variance run to run, and — under GPU time-slicing — invisible to DCGM, which reports one physical GPU's utilization regardless of how many pods are sharing it.

## What's next

Follow-on work once this skeleton has real numbers: KServe's newer `LLMInferenceService` API, the GKE Inference Gateway, Dynamic Resource Allocation (DRA) as a GPU-sharing mechanism, and a GCS results bucket to replace the RWO-PVC hand-off in `gpubench collect` (`docs/adr/0004-argocd-owns-platform-harness-owns-experiments.md`).
