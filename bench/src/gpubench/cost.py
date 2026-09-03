"""Cost per million tokens from GPU hourly price and measured throughput."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel

SECONDS_PER_HOUR = 3600.0
MILLION = 1_000_000.0


class PriceRow(BaseModel):
    key: str
    gpu: str
    machine_type: str
    region: str
    usd_per_hour: float
    source: str
    as_of: date


class CostSummary(BaseModel):
    usd_per_hour: float
    per_million_output: float
    per_million_total: float
    per_million_output_at_50: float
    per_million_output_at_25: float


def load_prices(path: Path) -> dict[str, PriceRow]:
    with path.open() as handle:
        rows = [PriceRow.model_validate(item) for item in yaml.safe_load(handle)]
    return {row.key: row for row in rows}


def cost_per_million(usd_per_hour: float, tokens_per_s: float) -> float:
    if tokens_per_s <= 0:
        raise ValueError("tokens_per_s must be positive")
    return usd_per_hour / (tokens_per_s * SECONDS_PER_HOUR) * MILLION


def utilization_adjusted(cost: float, utilization: float) -> float:
    if not 0 < utilization <= 1:
        raise ValueError("utilization must be in (0, 1]")
    return cost / utilization


def summarize_cost(price: PriceRow, output_tps: float, total_tps: float) -> CostSummary:
    output = cost_per_million(price.usd_per_hour, output_tps)
    return CostSummary(
        usd_per_hour=price.usd_per_hour,
        per_million_output=output,
        per_million_total=cost_per_million(price.usd_per_hour, total_tps),
        per_million_output_at_50=utilization_adjusted(output, 0.5),
        per_million_output_at_25=utilization_adjusted(output, 0.25),
    )
