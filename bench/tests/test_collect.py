import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gpubench.collect import build_manifest, collect, reader_pod_manifest
from gpubench.config import Experiment
from gpubench.cost import load_prices

PRICES = Path(__file__).resolve().parents[1] / "prices.yaml"
EXP = Experiment.model_validate(
    {
        "name": "baseline-l4",
        "kind": "engine",
        "variants": [{"name": "fp8"}],
        "loads": [{"max_concurrency": 1}],
    }
)


def test_reader_pod_mounts_results_pvc() -> None:
    pod = reader_pod_manifest()
    assert pod["kind"] == "Pod" and pod["metadata"]["namespace"] == "bench"
    assert pod["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"] == "bench-results"


def test_manifest_records_provenance() -> None:
    nodes = [
        {
            "metadata": {
                "labels": {
                    "cloud.google.com/gke-gpu-driver-version": "580.65.06",
                    "gpu": "nvidia-l4",
                }
            }
        }
    ]
    manifest = build_manifest(
        EXP, "deadbeef", ["img@sha256:1"], nodes, load_prices(PRICES)["l4-spot"]
    )
    assert manifest["git_sha"] == "deadbeef"
    assert manifest["image_ids"] == ["img@sha256:1"]
    assert manifest["gpu_driver_versions"] == ["580.65.06"]
    assert manifest["price"]["usd_per_hour"] == 0.424
    assert manifest["experiment"]["name"] == "baseline-l4"
    assert "collected_at" in manifest


def test_collect_copies_results_and_writes_manifest(tmp_path: Path) -> None:
    kube = MagicMock()
    kube.job_image_ids.return_value = ["img@sha256:1"]
    kube.node_labels.return_value = []
    kube.job_times.return_value = (None, None)
    kube.job_gpu_request.return_value = 1
    out = collect(EXP, tmp_path / "2026-11-01-baseline-l4", PRICES, kube, git_sha="abc")
    kube.apply.assert_called_once()
    kube.wait_pod_ready.assert_called_once_with("bench-reader", "bench", timeout_s=300)
    kube.cp_from.assert_called_once_with(
        "bench", "bench-reader", "/results/baseline-l4", out / "raw"
    )
    kube.delete.assert_called_once_with("pod", "bench-reader", "bench")
    assert (out / "manifest.json").exists()


def test_collect_deletes_reader_pod_when_wait_fails(tmp_path: Path) -> None:
    kube = MagicMock()
    kube.job_image_ids.return_value = ["img@sha256:1"]
    kube.node_labels.return_value = []
    kube.job_times.return_value = (None, None)
    kube.job_gpu_request.return_value = 1
    kube.wait_pod_ready.side_effect = RuntimeError("not ready")
    with pytest.raises(RuntimeError):
        collect(EXP, tmp_path / "out", PRICES, kube, git_sha="abc")
    kube.delete.assert_called_once_with("pod", "bench-reader", "bench")
    assert not (tmp_path / "out" / "manifest.json").exists()


def test_manifest_prices_gpu_hours() -> None:
    jobs = [
        {"name": "a", "start": "s", "end": "e", "seconds": 1800.0, "gpus": 1},
        {"name": "b", "start": "s", "end": "e", "seconds": 3600.0, "gpus": 1},
    ]
    manifest = build_manifest(EXP, "sha", [], [], load_prices(PRICES)["l4-spot"], jobs)
    assert manifest["jobs"] == jobs
    assert manifest["gpu_hours"] == 1.5
    assert manifest["usd"] == 0.636
    assert "spend_note" in manifest


def test_collect_records_job_timings(tmp_path: Path) -> None:
    kube = MagicMock()
    kube.job_image_ids.return_value = []
    kube.node_labels.return_value = []
    kube.job_times.return_value = ("2026-11-01T10:00:00Z", "2026-11-01T10:30:00Z")
    kube.job_gpu_request.return_value = 1
    out = collect(EXP, tmp_path / "out", PRICES, kube, git_sha="abc")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["jobs"][0]["name"] == "bench-baseline-l4-fp8"
    assert manifest["jobs"][0]["seconds"] == 1800.0
    assert manifest["gpu_hours"] == 0.5
    assert manifest["usd"] == 0.212
