from pathlib import Path
from unittest.mock import MagicMock

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
    out = collect(EXP, tmp_path / "2026-11-01-baseline-l4", PRICES, kube, git_sha="abc")
    kube.apply.assert_called_once()
    kube.wait_pod_ready.assert_called_once_with("bench-reader", "bench", timeout_s=300)
    kube.cp_from.assert_called_once_with(
        "bench", "bench-reader", "/results/baseline-l4", out / "raw"
    )
    kube.delete.assert_called_once_with("pod", "bench-reader", "bench")
    assert (out / "manifest.json").exists()
