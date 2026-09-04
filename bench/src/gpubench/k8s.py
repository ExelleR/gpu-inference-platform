"""Thin kubectl wrapper. Every method shells out; tests mock subprocess.run and time."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import yaml

POLL_INTERVAL_S = 15


class Kubectl:
    def run(self, args: list[str], input_text: str | None = None) -> str:
        try:
            completed = subprocess.run(
                ["kubectl", *args], input=input_text, text=True, capture_output=True, check=True
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(
                f"kubectl {' '.join(args)} failed (exit {exc.returncode}): {stderr}"
            ) from exc
        return completed.stdout

    def apply(self, manifests: list[dict]) -> str:
        return self.run(
            ["apply", "-f", "-"], input_text=yaml.safe_dump_all(manifests, sort_keys=False)
        )

    def wait_job(self, name: str, namespace: str, timeout_s: int) -> None:
        """Poll the Job until it is Complete; raise on a Failed condition or after timeout_s."""
        deadline = time.monotonic() + timeout_s
        while True:
            out = self.run(["-n", namespace, "get", "job", name, "-o", "json"])
            for cond in json.loads(out).get("status", {}).get("conditions") or []:
                if cond.get("status") != "True":
                    continue
                if cond.get("type") == "Complete":
                    return
                if cond.get("type") == "Failed":
                    detail = ": ".join(filter(None, [cond.get("reason"), cond.get("message")]))
                    raise RuntimeError(f"job/{name} in {namespace} failed: {detail}")
            if time.monotonic() >= deadline:
                raise TimeoutError(f"job/{name} in {namespace} not complete after {timeout_s}s")
            time.sleep(POLL_INTERVAL_S)

    def wait_pod_ready(self, name: str, namespace: str, timeout_s: int) -> None:
        self.run(
            [
                "-n",
                namespace,
                "wait",
                "--for=condition=ready",
                f"pod/{name}",
                f"--timeout={timeout_s}s",
            ]
        )

    def job_image_ids(self, name: str, namespace: str) -> list[str]:
        out = self.run(["-n", namespace, "get", "pods", "-l", f"job-name={name}", "-o", "json"])
        return [
            image_id
            for item in json.loads(out).get("items", [])
            for status in item.get("status", {}).get("containerStatuses", [])
            if (image_id := status.get("imageID", ""))
        ]

    def node_labels(self, selector: str) -> list[dict]:
        out = self.run(["get", "nodes", "-l", selector, "-o", "json"])
        return json.loads(out).get("items", [])

    def cp_from(self, namespace: str, pod: str, src: str, dst: str | Path) -> None:
        self.run(["cp", f"{namespace}/{pod}:{src}", str(dst)])

    def delete(self, kind: str, name: str, namespace: str) -> None:
        self.run(["-n", namespace, "delete", kind, name, "--ignore-not-found"])
