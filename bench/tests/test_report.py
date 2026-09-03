from pathlib import Path

from gpubench.cost import load_prices
from gpubench.parse import load_result
from gpubench.report import build_rows, to_markdown, write_summary

PRICES = Path(__file__).resolve().parents[1] / "prices.yaml"


def _results_dir(tmp_path: Path, fixtures_dir: Path) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    src = (fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text()
    (raw / "c16-run1.json").write_text(src)
    modified_src = src.replace('"output_throughput": 613.9', '"output_throughput": 600.1')
    (raw / "c16-run2.json").write_text(modified_src)
    return tmp_path


def test_rows_average_runs_and_price_them(fixtures_dir: Path) -> None:
    result = load_result(fixtures_dir / "vllm-bench-serve-v0.28.0.json")
    rows = build_rows([result, result], load_prices(PRICES))
    assert len(rows) == 1
    row = rows[0]
    assert row.label == "fp8-defaults" and row.concurrency == 16 and row.runs == 2
    assert row.output_tps == 613.9
    assert row.error_rate == 0.01
    assert row.usd_per_million_output > 0
    assert row.usd_per_million_output_at_50 == 2 * row.usd_per_million_output


def test_markdown_has_header_and_row(fixtures_dir: Path) -> None:
    result = load_result(fixtures_dir / "vllm-bench-serve-v0.28.0.json")
    md = to_markdown(build_rows([result], load_prices(PRICES)))
    assert "| label | concurrency |" in md
    assert "| fp8-defaults | 16 |" in md


def test_write_summary_creates_markdown_and_charts(tmp_path: Path, fixtures_dir: Path) -> None:
    results_dir = _results_dir(tmp_path, fixtures_dir)
    summary = write_summary(results_dir, PRICES)
    assert summary.name == "summary.md" and summary.exists()
    assert (results_dir / "charts" / "throughput.svg").exists()
    assert (results_dir / "charts" / "cost.svg").exists()
    assert "fp8-defaults" in summary.read_text()
