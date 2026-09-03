"""Copy benchmark output from the results PVC and record provenance."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from gpubench.config import Experiment
from gpubench.cost import PriceRow, load_prices
from gpubench.k8s import Kubectl
from gpubench.render import NAMESPACE, PVC_NAME, job_names

READER_POD = "bench-reader"


def reader_pod_manifest() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": READER_POD, "namespace": NAMESPACE},
        "spec": {
            "restartPolicy": "Never",
            "nodeSelector": {"pool": "system"},
            "containers": [
                {
                    "name": "reader",
                    "image": "busybox:1.36",
                    "command": ["sleep", "3600"],
                    "volumeMounts": [
                        {"name": "results", "mountPath": "/results", "readOnly": True}
                    ],
                }
            ],
            "volumes": [{"name": "results", "persistentVolumeClaim": {"claimName": PVC_NAME}}],
        },
    }


def current_git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], text=True, capture_output=True, check=True
    ).stdout.strip()


def build_manifest(
    exp: Experiment, sha: str, image_ids: list[str], nodes: list[dict], price: PriceRow
) -> dict:
    drivers = sorted(
        {
            n.get("metadata", {})
            .get("labels", {})
            .get("cloud.google.com/gke-gpu-driver-version", "")
            for n in nodes
        }
        - {""}
    )
    return {
        "collected_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": sha,
        "experiment": exp.model_dump(mode="json"),
        "image_ids": image_ids,
        "gpu_driver_versions": drivers,
        "price": price.model_dump(mode="json"),
    }


def collect(
    exp: Experiment, out_dir: Path, prices_path: Path, kube: Kubectl, git_sha: str | None = None
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    image_ids = [image for name in job_names(exp) for image in kube.job_image_ids(name, NAMESPACE)]
    nodes = kube.node_labels(f"gpu={exp.accelerator}")
    kube.apply([reader_pod_manifest()])
    try:
        kube.wait_pod_ready(READER_POD, NAMESPACE, timeout_s=300)
        kube.cp_from(NAMESPACE, READER_POD, f"/results/{exp.name}", out_dir / "raw")
    finally:
        kube.delete("pod", READER_POD, NAMESPACE)
    price = load_prices(prices_path)[exp.gpu_pool]
    manifest = build_manifest(exp, git_sha or current_git_sha(), image_ids, nodes, price)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return out_dir
