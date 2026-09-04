"""Aggregate results per (label, concurrency), price them, and write summary.md with charts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path, PurePosixPath
from statistics import mean

import matplotlib
from pydantic import BaseModel

from gpubench.cost import PriceRow, load_prices, summarize_cost
from gpubench.parse import RunResult, load_results

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


class Row(BaseModel):
    label: str
    gpu: str
    concurrency: int
    runs: int
    output_tps: float
    total_tps: float
    ttft_p50_ms: float
    ttft_p99_ms: float
    tpot_p50_ms: float
    tpot_p99_ms: float
    e2el_p99_ms: float | None
    goodput_rps: float | None
    error_rate: float
    usd_per_hour: float
    usd_per_million_output: float
    usd_per_million_total: float
    usd_per_million_output_at_50: float
    usd_per_million_output_at_25: float


def _label(result: RunResult) -> str:
    """Variant/target name, plus the server-sweep combination when the run belongs to one.

    `vllm bench sweep serve` writes each run under
    `<variant>/sweep/SERVE--<serve params>-BENCH--<bench params>/run=N.json` (no SERVE part
    without a server sweep). The serve part becomes a label suffix so combinations report as
    separate rows; the bench part is already the row's concurrency. Files directly under the
    variant/target or `sweep` keep the plain label; any other parent directory is appended.
    """
    base = result.metadata.get("variant") or result.metadata.get("target") or result.model_id
    parent = PurePosixPath(result.metadata.get("path", "")).parent.name
    if not parent or parent in {base, "sweep"} or parent.startswith("BENCH-"):
        return base
    if parent.startswith("SERVE-"):
        serve = parent.removeprefix("SERVE-").split("-BENCH-", 1)[0].strip("-")
        return f"{base}/{serve}"
    return f"{base}/{parent}"


def build_rows(results: list[RunResult], prices: dict[str, PriceRow]) -> list[Row]:
    groups: dict[tuple[str, str, int], list[RunResult]] = defaultdict(list)
    for result in results:
        key = (_label(result), result.metadata.get("gpu", "unknown"), result.max_concurrency or 0)
        groups[key].append(result)
    rows = []
    for (label, gpu, concurrency), group in sorted(groups.items()):
        if gpu not in prices:
            raise KeyError(f"no price row for gpu={gpu!r}; add it to prices.yaml")
        output_tps = mean(r.output_throughput for r in group)
        total_tps = mean(r.total_token_throughput for r in group)
        cost = summarize_cost(prices[gpu], output_tps=output_tps, total_tps=total_tps)
        goodputs = [r.request_goodput for r in group if r.request_goodput is not None]
        e2els = [r.e2el.p(99) for r in group if r.e2el is not None and 99 in r.e2el.percentiles_ms]
        rows.append(
            Row(
                label=label,
                gpu=gpu,
                concurrency=concurrency,
                runs=len(group),
                output_tps=round(output_tps, 1),
                total_tps=round(total_tps, 1),
                ttft_p50_ms=mean(r.ttft.p(50) for r in group),
                ttft_p99_ms=mean(r.ttft.p(99) for r in group),
                tpot_p50_ms=mean(r.tpot.p(50) for r in group),
                tpot_p99_ms=mean(r.tpot.p(99) for r in group),
                e2el_p99_ms=mean(e2els) if e2els else None,
                goodput_rps=mean(goodputs) if goodputs else None,
                error_rate=mean(r.error_rate for r in group),
                usd_per_hour=cost.usd_per_hour,
                usd_per_million_output=cost.per_million_output,
                usd_per_million_total=cost.per_million_total,
                usd_per_million_output_at_50=cost.per_million_output_at_50,
                usd_per_million_output_at_25=cost.per_million_output_at_25,
            )
        )
    return rows


COLUMNS = [
    ("label", "label"),
    ("concurrency", "concurrency"),
    ("runs", "runs"),
    ("output tok/s", "output_tps"),
    ("total tok/s", "total_tps"),
    ("TTFT p50 ms", "ttft_p50_ms"),
    ("TTFT p99 ms", "ttft_p99_ms"),
    ("TPOT p50 ms", "tpot_p50_ms"),
    ("TPOT p99 ms", "tpot_p99_ms"),
    ("E2E p99 ms", "e2el_p99_ms"),
    ("goodput req/s", "goodput_rps"),
    ("error rate", "error_rate"),
    ("$/M output", "usd_per_million_output"),
    ("$/M total", "usd_per_million_total"),
    ("$/M output @50%", "usd_per_million_output_at_50"),
    ("$/M output @25%", "usd_per_million_output_at_25"),
]


def _fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}" if value < 1 else f"{value:.1f}"
    return str(value)


def to_markdown(rows: list[Row]) -> str:
    header = "| " + " | ".join(title for title, _ in COLUMNS) + " |"
    sep = "|" + "|".join(" --- " for _ in COLUMNS) + "|"
    body = [
        "| " + " | ".join(_fmt(getattr(row, attr)) for _, attr in COLUMNS) + " |" for row in rows
    ]
    return "\n".join([header, sep, *body]) + "\n"


def plot_rows(rows: list[Row], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, attr, ylabel in [
        ("throughput.svg", "output_tps", "output tokens / s"),
        ("cost.svg", "usd_per_million_output", "USD per 1M output tokens"),
    ]:
        fig, ax = plt.subplots(figsize=(7, 4))
        for label in sorted({row.label for row in rows}):
            series = sorted(
                (row for row in rows if row.label == label), key=lambda r: r.concurrency
            )
            x_vals = [r.concurrency for r in series]
            y_vals = [getattr(r, attr) for r in series]
            ax.plot(x_vals, y_vals, marker="o", label=label)
        ax.set_xscale("log", base=2)
        ax.set_xlabel("max concurrency")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        ax.legend()
        path = out_dir / filename
        fig.savefig(path, format="svg", bbox_inches="tight")
        plt.close(fig)
        written.append(path)
    return written


def write_summary(results_dir: Path, prices_path: Path) -> Path:
    rows = build_rows(load_results(results_dir / "raw"), load_prices(prices_path))
    charts = plot_rows(rows, results_dir / "charts")
    cost_msg = "cost = $/h ÷ (tok/s × 3600) × 1e6"
    body = [
        f"# {results_dir.name}",
        "",
        f"Generated by `gpubench report`. Prices from `bench/prices.yaml`; {cost_msg}.",
        "",
        to_markdown(rows),
        *[f"![{chart.stem}](charts/{chart.name})" for chart in charts],
        "",
    ]
    summary = results_dir / "summary.md"
    summary.write_text("\n".join(body))
    return summary
