"""Render Kubernetes manifests (as dicts) for benchmark Jobs."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import yaml

from gpubench.config import Experiment, Target, Variant

NAMESPACE = "bench"
PVC_NAME = "bench-results"
DATASET_PATH = "/data/sharegpt.json"
CURL_IMAGE = "curlimages/curl:8.10.1"
GPU_RESOURCES = {
    "requests": {"cpu": "2", "memory": "9Gi", "ephemeral-storage": "20Gi", "nvidia.com/gpu": 1},
    "limits": {"memory": "10Gi", "nvidia.com/gpu": 1},
}
CLIENT_RESOURCES = {"requests": {"cpu": "1", "memory": "2Gi"}, "limits": {"memory": "4Gi"}}
GPU_TOLERATION = {"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"}


def job_name(exp: Experiment, item_name: str) -> str:
    """Generate a Kubernetes Job name from an experiment and item (variant or target)."""
    return f"bench-{exp.name}-{item_name}"[:63].rstrip("-")


def pvc_manifest() -> dict:
    return {
        "apiVersion": "v1",
        "kind": "PersistentVolumeClaim",
        "metadata": {"name": PVC_NAME, "namespace": NAMESPACE},
        "spec": {
            "accessModes": ["ReadWriteOnce"],
            "storageClassName": "standard-rwo",
            "resources": {"requests": {"storage": "20Gi"}},
        },
    }


def serve_params(variant: Variant) -> list[dict]:
    return variant.sweep_combinations()


def bench_params(exp: Experiment) -> list[dict]:
    params = []
    for load in exp.loads:
        row: dict = {"max-concurrency": load.max_concurrency, "num-prompts": load.num_prompts}
        if load.request_rate is not None:
            row["request-rate"] = load.request_rate
        params.append(row)
    return params


def _dataset_args(exp: Experiment) -> list[str]:
    ds = exp.dataset
    if ds.name == "random":
        return [
            "--dataset-name",
            "random",
            "--random-input-len",
            str(ds.random_input_len),
            "--random-output-len",
            str(ds.random_output_len),
            "--random-range-ratio",
            str(ds.random_range_ratio),
        ]
    return ["--dataset-name", "sharegpt", "--dataset-path", DATASET_PATH]


def _common_bench_args(exp: Experiment, metadata: dict[str, str]) -> list[str]:
    args = [
        *_dataset_args(exp),
        "--save-result",
        "--percentile-metrics",
        "ttft,tpot,itl,e2el",
        "--metric-percentiles",
        ",".join(str(p) for p in exp.percentiles),
        "--goodput",
        *[f"{k}:{v:g}" for k, v in exp.goodput.items()],
        "--seed",
        str(exp.seed),
        "--metadata",
        *[f"{k}={v}" for k, v in metadata.items()],
    ]
    return args


def _dataset_init_container(exp: Experiment) -> list[dict]:
    if exp.dataset.name != "sharegpt":
        return []
    check = ""
    if exp.dataset.sha256:
        check = f" && echo '{exp.dataset.sha256}  {DATASET_PATH}' | sha256sum -c -"
    return [
        {
            "name": "dataset",
            "image": CURL_IMAGE,
            "command": ["/bin/sh", "-c"],
            "args": [f"curl -fsSL {shlex.quote(exp.dataset.url)} -o {DATASET_PATH}{check}"],
            "volumeMounts": [{"name": "data", "mountPath": "/data"}],
        }
    ]


def _job(name: str, pod_spec: dict) -> dict:
    labels = {"app.kubernetes.io/part-of": "gpubench"}
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 86400,
            "activeDeadlineSeconds": 14400,
            "template": {"metadata": {"labels": labels}, "spec": pod_spec},
        },
    }


def engine_job(exp: Experiment, variant: Variant) -> tuple[dict, dict]:
    name = job_name(exp, variant.name)
    metadata = {"experiment": exp.name, "variant": variant.name, "gpu": exp.gpu_pool}
    serve_cmd = " ".join(
        [
            "vllm",
            "serve",
            variant.model,
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--served-model-name",
            variant.served_name,
            *variant.server_args,
        ]
    )
    bench_cmd = " ".join(
        [
            "vllm",
            "bench",
            "serve",
            "--backend",
            "openai",
            "--base-url",
            "http://127.0.0.1:8000",
            "--model",
            variant.model,
            "--served-model-name",
            variant.served_name,
            *_common_bench_args(exp, metadata),
        ]
    )
    configmap = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "data": {
            "serve.json": json.dumps(serve_params(variant), indent=2),
            "bench.json": json.dumps(bench_params(exp), indent=2),
        },
    }
    args = [
        "vllm",
        "bench",
        "sweep",
        "serve",
        "--serve-cmd",
        serve_cmd,
        "--bench-cmd",
        bench_cmd,
        "--serve-params",
        "/config/serve.json",
        "--bench-params",
        "/config/bench.json",
        "--num-runs",
        str(exp.num_runs),
        "--server-ready-timeout",
        "900",
        "-o",
        f"/results/{exp.name}/{variant.name}",
        "-e",
        "sweep",
    ]
    pod_spec = {
        "restartPolicy": "Never",
        "priorityClassName": "bench-batch",
        "nodeSelector": {"cloud.google.com/gke-accelerator": exp.accelerator},
        "tolerations": [GPU_TOLERATION],
        "initContainers": _dataset_init_container(exp),
        "containers": [
            {
                "name": "sweep",
                "image": variant.image,
                "command": ["/bin/sh", "-c"],
                "args": [" ".join(shlex.quote(a) for a in args)],
                "env": [{"name": "HF_HOME", "value": "/data/hf"}],
                "resources": GPU_RESOURCES,
                "volumeMounts": [
                    {"name": "results", "mountPath": "/results"},
                    {"name": "config", "mountPath": "/config"},
                    {"name": "data", "mountPath": "/data"},
                    {"name": "shm", "mountPath": "/dev/shm"},
                ],
            }
        ],
        "volumes": [
            {"name": "results", "persistentVolumeClaim": {"claimName": PVC_NAME}},
            {"name": "config", "configMap": {"name": name}},
            {"name": "data", "emptyDir": {"sizeLimit": "40Gi"}},
            {"name": "shm", "emptyDir": {"medium": "Memory", "sizeLimit": "1Gi"}},
        ],
    }
    return configmap, _job(name, pod_spec)


def platform_job(exp: Experiment, target: Target) -> dict:
    name = job_name(exp, target.name)
    metadata = {"experiment": exp.name, "target": target.name, "gpu": exp.gpu_pool}
    commands = []
    for run in range(1, exp.num_runs + 1):
        for load in exp.loads:
            args = [
                "vllm",
                "bench",
                "serve",
                "--backend",
                "openai",
                "--base-url",
                target.url,
                "--model",
                target.model,
                "--served-model-name",
                target.served_model,
                "--max-concurrency",
                str(load.max_concurrency),
                "--num-prompts",
                str(load.num_prompts),
                *(
                    ["--request-rate", str(load.request_rate)]
                    if load.request_rate is not None
                    else []
                ),
                *_common_bench_args(exp, metadata),
                "--result-dir",
                f"/results/{exp.name}/{target.name}",
                "--result-filename",
                f"c{load.max_concurrency}-run{run}.json",
            ]
            commands.append(" ".join(shlex.quote(a) for a in args))
    pod_spec = {
        "restartPolicy": "Never",
        "priorityClassName": "bench-batch",
        "nodeSelector": {"pool": "system"},
        "initContainers": _dataset_init_container(exp),
        "containers": [
            {
                "name": "client",
                "image": exp.client_image,
                "command": ["/bin/sh", "-c"],
                "args": [" && ".join(commands)],
                "env": [{"name": "HF_HOME", "value": "/data/hf"}],
                "resources": CLIENT_RESOURCES,
                "volumeMounts": [
                    {"name": "results", "mountPath": "/results"},
                    {"name": "data", "mountPath": "/data"},
                ],
            }
        ],
        "volumes": [
            {"name": "results", "persistentVolumeClaim": {"claimName": PVC_NAME}},
            {"name": "data", "emptyDir": {"sizeLimit": "10Gi"}},
        ],
    }
    return _job(name, pod_spec)


def job_names(exp: Experiment) -> list[str]:
    items = exp.variants if exp.kind == "engine" else exp.targets
    return [job_name(exp, item.name) for item in items]


def render_experiment(exp: Experiment) -> list[dict]:
    manifests = [pvc_manifest()]
    if exp.kind == "engine":
        for variant in exp.variants:
            manifests.extend(engine_job(exp, variant))
    else:
        manifests.extend(platform_job(exp, target) for target in exp.targets)
    return manifests


def dump_manifests(manifests: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump_all(manifests, sort_keys=False))
