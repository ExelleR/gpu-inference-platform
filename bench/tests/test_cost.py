from pathlib import Path

import pytest

from gpubench.cost import cost_per_million, load_prices, summarize_cost, utilization_adjusted

PRICES = Path(__file__).resolve().parents[1] / "prices.yaml"


def test_cost_per_million_matches_formula() -> None:
    # 0.424 $/h at 500 tok/s -> 0.424 / (500*3600) * 1e6
    assert cost_per_million(0.424, 500.0) == pytest.approx(0.23556, rel=1e-3)


def test_zero_throughput_is_an_error() -> None:
    with pytest.raises(ValueError):
        cost_per_million(0.424, 0.0)


def test_utilization_adjusted_scales_inversely() -> None:
    assert utilization_adjusted(1.0, 0.5) == pytest.approx(2.0)
    with pytest.raises(ValueError):
        utilization_adjusted(1.0, 0.0)


def test_load_prices_keys_and_fields() -> None:
    prices = load_prices(PRICES)
    assert prices["l4-spot"].usd_per_hour == pytest.approx(0.424)
    assert prices["a100-40gb-spot"].machine_type == "a2-highgpu-1g"


def test_summarize_cost_reports_all_views() -> None:
    price = load_prices(PRICES)["l4-spot"]
    summary = summarize_cost(price, output_tps=500.0, total_tps=1000.0)
    assert summary.per_million_output == pytest.approx(0.23556, rel=1e-3)
    assert summary.per_million_total == pytest.approx(0.11778, rel=1e-3)
    assert summary.per_million_output_at_50 == pytest.approx(0.47111, rel=1e-3)
    assert summary.per_million_output_at_25 == pytest.approx(0.94222, rel=1e-3)
