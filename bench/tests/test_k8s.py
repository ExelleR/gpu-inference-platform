import json
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from gpubench.k8s import Kubectl


def test_apply_streams_yaml_to_kubectl() -> None:
    kube = Kubectl()
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = "ok"
        kube.apply([{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "bench"}}])
    args, kwargs = run.call_args
    assert args[0][:3] == ["kubectl", "apply", "-f"] and args[0][3] == "-"
    assert "kind: Namespace" in kwargs["input"]


def _job_json(conditions: list[dict]) -> str:
    return json.dumps({"status": {"conditions": conditions}})


def test_wait_job_polls_get_job_until_complete() -> None:
    kube = Kubectl()
    with patch("gpubench.k8s.subprocess.run") as run, patch("gpubench.k8s.time.sleep") as sleep:
        run.side_effect = [
            MagicMock(stdout=json.dumps({"status": {}})),
            MagicMock(stdout=_job_json([{"type": "Complete", "status": "True"}])),
        ]
        kube.wait_job("bench-x", "bench", timeout_s=30)
    assert run.call_count == 2
    assert run.call_args[0][0] == ["kubectl", "-n", "bench", "get", "job", "bench-x", "-o", "json"]
    assert sleep.call_args_list == [call(15)]


def test_wait_job_raises_with_the_failed_condition_message() -> None:
    kube = Kubectl()
    failed = {
        "type": "Failed",
        "status": "True",
        "reason": "DeadlineExceeded",
        "message": "Job was active longer than specified deadline",
    }
    with patch("gpubench.k8s.subprocess.run") as run, patch("gpubench.k8s.time.sleep") as sleep:
        run.return_value.stdout = _job_json([failed])
        with pytest.raises(RuntimeError, match="DeadlineExceeded.*longer than specified deadline"):
            kube.wait_job("bench-x", "bench", timeout_s=30)
    sleep.assert_not_called()


def test_wait_job_times_out() -> None:
    kube = Kubectl()
    with patch("gpubench.k8s.subprocess.run") as run, patch("gpubench.k8s.time") as clock:
        run.return_value.stdout = _job_json([{"type": "Complete", "status": "False"}])
        clock.monotonic.side_effect = [0, 15, 31]
        with pytest.raises(TimeoutError, match="bench-x"):
            kube.wait_job("bench-x", "bench", timeout_s=30)
    assert clock.sleep.call_args_list == [call(15)]


def test_run_wraps_kubectl_failure_with_stderr() -> None:
    kube = Kubectl()
    with patch("gpubench.k8s.subprocess.run") as run:
        run.side_effect = subprocess.CalledProcessError(
            1,
            ["kubectl", "get", "job"],
            stderr='Error from server (NotFound): jobs "x" not found\n',
        )
        with pytest.raises(RuntimeError, match="NotFound"):
            kube.run(["get", "job", "x"])


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


def test_job_image_ids_skips_containers_without_image_id() -> None:
    kube = Kubectl()
    payload = (
        '{"items":['
        '{"status":{"containerStatuses":[{"imageID":"docker.io/x@sha256:abc"}]}},'
        '{"status":{"containerStatuses":[{"name":"container"}]}}'
        "]}"
    )
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = payload
        assert kube.job_image_ids("bench-x", "bench") == ["docker.io/x@sha256:abc"]


def test_wait_job_retries_transient_kubectl_failures() -> None:
    kube = Kubectl()
    err = subprocess.CalledProcessError(1, "kubectl", stderr="connection refused")
    with patch("gpubench.k8s.subprocess.run") as run, patch("gpubench.k8s.time.sleep") as sleep:
        done = MagicMock(stdout=_job_json([{"type": "Complete", "status": "True"}]))
        run.side_effect = [err, err, done]
        kube.wait_job("bench-x", "bench", timeout_s=60)
    assert run.call_count == 3
    assert sleep.call_args_list == [call(15), call(15)]


def test_wait_job_gives_up_after_repeated_kubectl_failures() -> None:
    kube = Kubectl()
    err = subprocess.CalledProcessError(1, "kubectl", stderr="connection refused")
    with patch("gpubench.k8s.subprocess.run") as run, patch("gpubench.k8s.time.sleep"):
        run.side_effect = [err] * 4
        with pytest.raises(RuntimeError, match="connection refused"):
            kube.wait_job("bench-x", "bench", timeout_s=60)
    assert run.call_count == 4


def test_job_times_parses_status_timestamps() -> None:
    kube = Kubectl()
    payload = json.dumps(
        {"status": {"startTime": "2026-11-01T10:00:00Z", "completionTime": "2026-11-01T10:30:00Z"}}
    )
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = payload
        assert kube.job_times("bench-x", "bench") == (
            "2026-11-01T10:00:00Z",
            "2026-11-01T10:30:00Z",
        )


def test_job_gpu_request_sums_container_limits() -> None:
    kube = Kubectl()
    containers = [
        {"resources": {"limits": {"nvidia.com/gpu": "1"}}},
        {"resources": {"limits": {"nvidia.com/gpu": 1}}},
    ]
    payload = json.dumps({"spec": {"template": {"spec": {"containers": containers}}}})
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = payload
        assert kube.job_gpu_request("bench-x", "bench") == 2


def test_job_gpu_request_is_zero_without_gpu() -> None:
    kube = Kubectl()
    payload = json.dumps({"spec": {"template": {"spec": {"containers": [{"resources": {}}]}}}})
    with patch("gpubench.k8s.subprocess.run") as run:
        run.return_value.stdout = payload
        assert kube.job_gpu_request("bench-x", "bench") == 0
