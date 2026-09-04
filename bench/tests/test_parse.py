import json
import math
from pathlib import Path

import pytest

from gpubench.parse import load_result, load_results, parse_result


def test_parse_fixture_core_fields(fixtures_dir: Path) -> None:
    result = load_result(fixtures_dir / "vllm-bench-serve-v0.28.0.json")
    assert result.model_id == "Qwen/Qwen3-8B-FP8"
    assert result.max_concurrency == 16
    assert math.isinf(result.request_rate)
    assert result.output_throughput == pytest.approx(613.9)
    assert result.ttft.p(99) == pytest.approx(480.7)
    assert result.tpot.median_ms == pytest.approx(23.5)
    assert result.e2el is not None and result.e2el.p(90) == pytest.approx(6000.0)
    assert result.error_rate == pytest.approx(0.01)
    assert result.metadata == {
        "experiment": "baseline-l4",
        "variant": "fp8-defaults",
        "gpu": "l4-spot",
    }


def test_raw_arrays_and_private_keys_are_dropped(fixtures_dir: Path) -> None:
    data = json.loads((fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text())
    result = parse_result(data)
    assert "ttfts" not in result.metadata and "_note" not in result.metadata


def test_missing_optional_percentile_group_is_none(fixtures_dir: Path) -> None:
    data = json.loads((fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text())
    for key in [k for k in data if k.endswith("_e2el_ms")]:
        del data[key]
    assert parse_result(data).e2el is None


def test_load_results_skips_manifest(tmp_path: Path, fixtures_dir: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "c16-run1.json").write_text((fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text())
    (tmp_path / "manifest.json").write_text("{}")
    assert len(load_results(tmp_path)) == 1


SWEEP_DIR = (
    "grid/sweep/SERVE--max-num-seqs=64-max-num-batched-tokens=2048"
    "-BENCH--max-concurrency=16-num-prompts=200"
)


def test_load_results_skips_summaries_and_non_results_and_records_path(
    tmp_path: Path, fixtures_dir: Path
) -> None:
    src = (fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text()
    comb = tmp_path / SWEEP_DIR
    comb.mkdir(parents=True)
    (comb / "run=0.json").write_text(src)
    (comb / "summary.json").write_text(f"[{src}]")  # vllm's per-combination summary: a JSON list
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "grid" / "notes.json").write_text('{"note": "no benchmark fields"}')
    results = load_results(tmp_path)
    assert len(results) == 1
    assert results[0].metadata["path"] == f"{SWEEP_DIR}/run=0.json"
    assert results[0].metadata["variant"] == "fp8-defaults"
