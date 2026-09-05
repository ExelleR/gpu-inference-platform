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


def _seconds_between(start: str | None, end: str | None) -> float:
    if not start or not end:
        return 0.0
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def job_rows(exp: Experiment, kube: Kubectl) -> list[dict]:
    """Start, end, duration and GPU count per Job; Jobs already garbage-collected are skipped."""
    rows = []
    for name in job_names(exp):
        try:
            start, end = kube.job_times(name, NAMESPACE)
            gpus = kube.job_gpu_request(name, NAMESPACE)
        except (RuntimeError, KeyError):
            continue
        rows.append(
            {
                "name": name,
                "start": start,
                "end": end,
                "seconds": _seconds_between(start, end),
                "gpus": gpus,
            }
        )
    return rows


SPEND_NOTE = (
    "engine Jobs only, priced at the whole-VM rate (one GPU per VM); platform experiments' "
    "servers are billed by the serving tier, not by these Jobs"
)


def build_manifest(
    exp: Experiment,
    sha: str,
    image_ids: list[str],
    nodes: list[dict],
    price: PriceRow,
    jobs: list[dict] | None = None,
) -> dict:
    jobs = jobs or []
    gpu_hours = sum(j["seconds"] * j["gpus"] for j in jobs) / 3600.0
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
        "jobs": jobs,
        "gpu_hours": round(gpu_hours, 4),
        "usd": round(gpu_hours * price.usd_per_hour, 4),
        "spend_note": SPEND_NOTE,
    }


def collect(
    exp: Experiment, out_dir: Path, prices_path: Path, kube: Kubectl, git_sha: str | None = None
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    image_ids = [image for name in job_names(exp) for image in kube.job_image_ids(name, NAMESPACE)]
    nodes = kube.node_labels(f"gpu={exp.accelerator}")
    jobs = job_rows(exp, kube)
    kube.apply([reader_pod_manifest()])
    try:
        kube.wait_pod_ready(READER_POD, NAMESPACE, timeout_s=300)
        kube.cp_from(NAMESPACE, READER_POD, f"/results/{exp.name}", out_dir / "raw")
    finally:
        kube.delete("pod", READER_POD, NAMESPACE)
    price = load_prices(prices_path)[exp.gpu_pool]
    manifest = build_manifest(exp, git_sha or current_git_sha(), image_ids, nodes, price, jobs)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return out_dir
