from unittest.mock import patch

from gpubench.k8s import Kubectl


def test_apply_streams_yaml_to_kubectl() -> None:
    kube = Kubectl()
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = "ok"
        kube.apply([{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "bench"}}])
    args, kwargs = run.call_args
    assert args[0][:3] == ["kubectl", "apply", "-f"] and args[0][3] == "-"
    assert "kind: Namespace" in kwargs["input"]


def test_wait_job_uses_condition_complete() -> None:
    kube = Kubectl()
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = ""
        kube.wait_job("bench-x", "bench", timeout_s=30)
    assert run.call_args[0][0] == [
        "kubectl",
        "-n",
        "bench",
        "wait",
        "--for=condition=complete",
        "job/bench-x",
        "--timeout=30s",
    ]


def test_job_image_ids_parses_json() -> None:
    kube = Kubectl()
    payload = (
        '{"items":[{"status":{"containerStatuses":[{"imageID":'
        '"docker.io/vllm/vllm-openai@sha256:abc"}]}}]}'
    )
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = payload
        image_id = "docker.io/vllm/vllm-openai@sha256:abc"
        assert kube.job_image_ids("bench-x", "bench") == [image_id]
