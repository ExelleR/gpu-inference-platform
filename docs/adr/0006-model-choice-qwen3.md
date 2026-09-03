# Qwen3-8B family as the benchmark model, `Qwen3-8B-FP8` default

Status: accepted
Date: 2026-09-01

## Context

The harness needs one model family it can pull and serve without a manual, per-user approval step, since the cluster is created and destroyed by an unattended `make up`/`make down` cycle and Hugging Face downloads happen inside benchmark Jobs. It also needs official low-bit quantized checkpoints to compare against bf16, since quantization is one of the platform's benchmark axes (`bench/experiments/02-quant-l4.yaml`).

## Decision

Standardize on the Qwen3 family, with `Qwen/Qwen3-8B-FP8` as the default model — `gpubench`'s `Variant.model` default, the raw vLLM chart's default, and the `InferenceService`'s `storageUri` all point at it. `Qwen/Qwen3-0.6B` and `Qwen/Qwen3-1.7B` cover the smoke test and the time-slicing experiment, where a full 8B model isn't needed. Qwen3 checkpoints are ungated on Hugging Face; Llama 3.1 and Gemma 3, by contrast, both require a manually-approved access request per account (`gated: manual`), which is incompatible with a cluster that may be rebuilt from scratch mid-session. Qwen also publishes first-party FP8 and AWQ quantized checkpoints directly under the `Qwen` org, rather than relying on community re-quantizations of varying quality.

## Consequences

The FP8 checkpoint does not behave identically across the platform's two GPU generations: on L4 (Ada Lovelace), it runs as true W8A8 using native FP8 tensor cores; on A100 (Ampere, no FP8 tensor cores), vLLM falls back to the Marlin kernel and effectively runs W8A16. This is a real hardware asymmetry, not a bug, and the results writeup must report it explicitly rather than presenting one FP8 number across both GPUs. On L4, bf16 `Qwen3-8B` at `--gpu-memory-utilization=0.92` (about 22 GB usable of 24 GB) leaves only around 6 GB for KV cache and activations after roughly 16 GB of bf16 weights — a meaningful part of the FP8 default's motivation, since FP8 roughly halves the weight footprint and frees that memory for longer context and higher concurrency.
