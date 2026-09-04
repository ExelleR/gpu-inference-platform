# Cost Model

This is the cost math `gpubench` applies to every measured run, implemented in
`bench/src/gpubench/cost.py` and used by `gpubench report` to build `summary.md`'s cost columns.

## Formula

```
$/1M output tokens = $/h ÷ (output tok/s × 3600) × 1e6
```

`$/h` is the whole-VM hourly price from `bench/prices.yaml` — a full `g2-standard-4` or
`a2-highgpu-1g`, not a fractional-GPU rate — and `output tok/s` is the run's measured output
throughput (`output_throughput` from vLLM's own benchmark JSON), meaned across a point's runs at
a given (label, GPU, concurrency) group — label being the variant name for engine experiments or
the target name for platform ones — per `docs/methodology.md`. A blended variant divides by
total tok/s instead (`total_token_throughput`, prompt plus generated tokens together), giving
$/1M total tokens — closer to how some hosted providers bill. `summarize_cost()` computes both
for every row.

## Utilization adjustment

The formula above assumes the GPU is saturated with requests for the full hour it's billed.
`gpubench` also reports the same cost adjusted for 100%, 50% and 25% utilization:
`cost_at_utilization = cost ÷ utilization`. At 100% the adjustment is a no-op (the raw formula's
own number); at 50% and 25% it doubles and quadruples the headline $/M figure, modeling a GPU
billed by the hour whether or not a request is in flight. `summary.md` prints `$/M output`,
`$/M output @50%` and `$/M output @25%` side by side for exactly this reason — a number that only
holds at 100% utilization overstates almost any real deployment.

## Price table

Whole-VM hourly prices, from `bench/prices.yaml` (source snapshot: gcloud-compute.com, generated
2026-08-30 from the Cloud Billing catalog):

| Key | GPU | Machine type | Region | USD/hour | As of |
| --- | --- | --- | --- | --- | --- |
| `l4-spot` | nvidia-l4 | g2-standard-4 | us-central1 | 0.424 | 2026-08-30 |
| `l4-ondemand` | nvidia-l4 | g2-standard-4 | us-central1 | 0.7068 | 2026-08-30 |
| `a100-40gb-spot` | nvidia-tesla-a100 | a2-highgpu-1g | us-central1 | 2.1208 | 2026-08-30 |
| `a100-40gb-ondemand` | nvidia-tesla-a100 | a2-highgpu-1g | us-central1 | 3.6734 | 2026-08-30 |

Both L4 rows come from [gcloud-compute.com/g2-standard-4.html](https://gcloud-compute.com/g2-standard-4.html);
both A100-40GB rows from [gcloud-compute.com/a2-highgpu-1g.html](https://gcloud-compute.com/a2-highgpu-1g.html).
Only `l4-spot` and `a100-40gb-spot` price any current experiment (`gpu_pool` in
`bench/experiments/*.yaml`); the on-demand rows exist for comparison. Prices drift — refresh
`as_of` when they're next checked.

## Sanity anchors

Two external, previously-published reference points — not our own measurements — for judging
whether a result is in a plausible range before trusting it:

- A100-40GB: ~2,100 output tok/s for a 7–8B-parameter model at 50 concurrent requests.
- A10-24GB running Qwen3-8B in fp16: ~850 output tok/s at 64 concurrent requests, degrading to
  87% request failures at 128 concurrent.

Neither anchor is reproduced directly by this repository's own experiments — none target an A10
pool, and the A100 anchor isn't model- or precision-matched to `Qwen3-8B-FP8` — but a measured L4
or A100 number that lands wildly outside this range, in either direction, is a reason to check the
harness before trusting the result.
