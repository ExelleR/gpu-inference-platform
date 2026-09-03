from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from gpubench.cli import app

runner = CliRunner()
ENGINE_YAML = """
name: smoke
kind: engine
variants: [{name: v}]
loads: [{max_concurrency: 1, num_prompts: 10}]
"""


def test_validate_ok_and_bad(tmp_path: Path) -> None:
    good = tmp_path / "good.yaml"
    good.write_text(ENGINE_YAML)
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nkind: engine\nloads: []\n")
    assert runner.invoke(app, ["validate", str(good)]).exit_code == 0
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1 and "bad.yaml" in result.output


def test_render_writes_one_file_per_experiment(tmp_path: Path) -> None:
    exp = tmp_path / "smoke.yaml"
    exp.write_text(ENGINE_YAML)
    out = tmp_path / "out"
    assert runner.invoke(app, ["render", str(exp), "-o", str(out)]).exit_code == 0
    assert (out / "smoke.yaml").exists()


def test_run_applies_and_waits(tmp_path: Path) -> None:
    exp = tmp_path / "smoke.yaml"
    exp.write_text(ENGINE_YAML)
    with patch("gpubench.cli.Kubectl") as kube_cls:
        kube = kube_cls.return_value
        result = runner.invoke(app, ["run", str(exp), "--timeout-s", "60"])
    assert result.exit_code == 0, result.output
    kube.apply.assert_called_once()
    kube.wait_job.assert_called_once_with("bench-smoke-v", "bench", timeout_s=60)


def test_report_writes_summary(tmp_path: Path, fixtures_dir: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "c16-run1.json").write_text((fixtures_dir / "vllm-bench-serve-v0.28.0.json").read_text())
    prices = Path(__file__).resolve().parents[1] / "prices.yaml"
    result = runner.invoke(app, ["report", str(tmp_path), "--prices", str(prices)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "summary.md").exists()
