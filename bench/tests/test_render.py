from pathlib import Path

import yaml

from gpubench.config import Experiment
from gpubench.render import (
    PVC_NAME,
    bench_params,
    dump_manifests,
    engine_job,
    job_names,
    platform_job,
    render_experiment,
    serve_params,
)

ENGINE = Experiment.model_validate(
    {
        "name": "baseline-l4",
        "kind": "engine",
        "variants": [
            {
                "name": "fp8",
                "server_args": ["--max-model-len", "8192"],
                "server_sweep": {"max-num-seqs": [64, 128]},
            }
        ],
        "loads": [
            {"max_concurrency": 1, "num_prompts": 50},
            {"max_concurrency": 16, "num_prompts": 200},
        ],
        "dataset": {"sha256": "abc123"},
    }
)

PLATFORM = Experiment.model_validate(
    {
        "name": "kserve-vs-raw",
        "kind": "platform",
        "targets": [
            {
                "name": "raw",
                "url": "http://vllm-baseline.inference.svc:8000",
                "model": "Qwen/Qwen3-8B-FP8",
                "served_model": "qwen3-8b",
            }
        ],
        "loads": [{"max_concurrency": 4, "num_prompts": 100}],
        "num_runs": 2,
    }
)


def test_serve_and_bench_params() -> None:
    assert serve_params(ENGINE.variants[0]) == [{"max-num-seqs": 64}, {"max-num-seqs": 128}]
    assert bench_params(ENGINE) == [
        {"max-concurrency": 1, "num-prompts": 50},
        {"max-concurrency": 16, "num-prompts": 200},
    ]


def test_engine_job_shape() -> None:
    configmap, job = engine_job(ENGINE, ENGINE.variants[0])
    assert configmap["kind"] == "ConfigMap"
    assert set(configmap["data"]) == {"serve.json", "bench.json"}
    pod = job["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert job["metadata"]["namespace"] == "bench"
    assert container["resources"]["limits"]["nvidia.com/gpu"] == 1
    assert pod["nodeSelector"] == {"cloud.google.com/gke-accelerator": "nvidia-l4"}
    assert pod["tolerations"][0]["key"] == "nvidia.com/gpu"
    assert pod["priorityClassName"] == "bench-batch"
    script = container["args"][0]
    assert "vllm bench sweep serve" in script
    assert "--serve-cmd" in script and "--num-runs" in script
    results_mount = any(
        m["name"] == "results" and m["mountPath"] == "/results" for m in container["volumeMounts"]
    )
    assert results_mount
    results_volume = any(
        v["name"] == "results" and v["persistentVolumeClaim"]["claimName"] == PVC_NAME
        for v in pod["volumes"]
    )
    assert results_volume
    init = pod["initContainers"][0]
    init_args = " ".join(init["args"])
    assert "sha256sum" in init_args and "abc123" in init_args


def test_platform_job_runs_every_load_and_run_against_target() -> None:
    job = platform_job(PLATFORM, PLATFORM.targets[0])
    pod = job["spec"]["template"]["spec"]
    script = " ".join(pod["containers"][0]["args"])
    assert pod["nodeSelector"] == {"pool": "system"}
    assert "nvidia.com/gpu" not in pod["containers"][0]["resources"].get("limits", {})
    assert script.count("vllm bench serve") == 2  # 1 load x 2 runs
    assert "--base-url http://vllm-baseline.inference.svc:8000" in script
    assert "c4-run2.json" in script


def test_render_and_dump(tmp_path: Path) -> None:
    manifests = render_experiment(ENGINE)
    assert [m["kind"] for m in manifests] == ["PersistentVolumeClaim", "ConfigMap", "Job"]
    assert job_names(ENGINE) == ["bench-baseline-l4-fp8"]
    out = tmp_path / "baseline-l4.yaml"
    dump_manifests(manifests, out)
    assert len(list(yaml.safe_load_all(out.read_text()))) == 3
