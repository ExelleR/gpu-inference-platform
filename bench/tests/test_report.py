from pathlib import Path

from gpubench.cost import load_prices
from gpubench.parse import load_result, load_results
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


SERVE_64 = (
    "SERVE--max-num-seqs=64-max-num-batched-tokens=2048-BENCH--max-concurrency=16-num-prompts=200"
)
SERVE_128 = (
    "SERVE--max-num-seqs=128-max-num-batched-tokens=2048-BENCH--max-concurrency=16-num-prompts=200"
)
BENCH_ONLY = "BENCH--max-concurrency=16-num-prompts=200"


def _write(raw: Path, rel: str, text: str) -> None:
    path = raw / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_sweep_combinations_become_separate_rows(tmp_path: Path, fixtures_dir: Path) -> None:
    src = (fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text()
    src = src.replace('"variant": "fp8-defaults"', '"variant": "grid"')
    raw = tmp_path / "raw"
    _write(raw, f"grid/sweep/{SERVE_64}/run=0.json", src)
    _write(raw, f"grid/sweep/{SERVE_128}/run=0.json", src)
    rows = build_rows(load_results(raw), load_prices(PRICES))
    assert sorted((row.label, row.concurrency, row.runs) for row in rows) == [
        ("grid/max-num-seqs=128-max-num-batched-tokens=2048", 16, 1),
        ("grid/max-num-seqs=64-max-num-batched-tokens=2048", 16, 1),
    ]


def test_bench_only_directory_keeps_the_plain_label(tmp_path: Path, fixtures_dir: Path) -> None:
    src = (fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text()
    raw = tmp_path / "raw"
    _write(raw, f"fp8-defaults/sweep/{BENCH_ONLY}/run=0.json", src)
    _write(raw, f"fp8-defaults/sweep/{BENCH_ONLY}/run=1.json", src)
    rows = build_rows(load_results(raw), load_prices(PRICES))
    assert [(row.label, row.runs) for row in rows] == [("fp8-defaults", 2)]


def test_other_parent_directories_are_appended_to_the_label(
    tmp_path: Path, fixtures_dir: Path
) -> None:
    src = (fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text()
    raw = tmp_path / "raw"
    _write(raw, "fp8-defaults/run=0.json", src)  # parent is the variant itself
    _write(raw, "fp8-defaults/sweep/run=0.json", src)  # parent is the sweep dir
    _write(raw, "fp8-defaults/extra/run=0.json", src)  # anything else is appended
    rows = build_rows(load_results(raw), load_prices(PRICES))
    assert [(row.label, row.runs) for row in rows] == [
        ("fp8-defaults", 2),
        ("fp8-defaults/extra", 1),
    ]


def test_write_summary_ignores_a_stray_summary_json(tmp_path: Path, fixtures_dir: Path) -> None:
    results_dir = _results_dir(tmp_path, fixtures_dir)
    (results_dir / "raw" / "summary.json").write_text("[]")
    summary = write_summary(results_dir, PRICES)
    assert "| fp8-defaults | 16 | 2 |" in summary.read_text()
