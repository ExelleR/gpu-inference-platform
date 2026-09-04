# Results

One directory per collected experiment: `results/<YYYY-MM-DD>-<experiment>/`.

| Path | Written by | Content |
| --- | --- | --- |
| `raw/**/*.json` | `vllm bench serve --save-result` inside the Job | untouched benchmark output (engine runs also carry vLLM's per-combination `summary.json` and `summary.csv`, which `report` ignores) |
| `manifest.json` | `gpubench collect` | git SHA, image digests, GPU driver versions, experiment definition, price row |
| `summary.md`, `charts/*.svg` | `gpubench report` | aggregated table and charts |

Raw files are committed on purpose: anyone can re-run `gpubench report` and get the same table.
