"""Thin kubectl wrapper. Every method shells out; tests mock subprocess.run."""

from __future__ import annotations

import json
import subprocess

import yaml


class Kubectl:
    def run(self, args: list[str], input_text: str | None = None) -> str:
        completed = subprocess.run(
            ["kubectl", *args], input=input_text, text=True, capture_output=True, check=True
        )
        return completed.stdout

    def apply(self, manifests: list[dict]) -> str:
        return self.run(
            ["apply", "-f", "-"], input_text=yaml.safe_dump_all(manifests, sort_keys=False)
        )

    def wait_job(self, name: str, namespace: str, timeout_s: int) -> None:
        self.run(
            [
                "-n",
                namespace,
                "wait",
                "--for=condition=complete",
                f"job/{name}",
                f"--timeout={timeout_s}s",
            ]
        )

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
            status["imageID"]
            for item in json.loads(out).get("items", [])
            for status in item.get("status", {}).get("containerStatuses", [])
        ]

    def node_labels(self, selector: str) -> list[dict]:
        out = self.run(["get", "nodes", "-l", selector, "-o", "json"])
        return json.loads(out).get("items", [])

    def cp_from(self, namespace: str, pod: str, src: str, dst) -> None:
        self.run(["cp", f"{namespace}/{pod}:{src}", str(dst)])

    def delete(self, kind: str, name: str, namespace: str) -> None:
        self.run(["-n", namespace, "delete", kind, name, "--ignore-not-found"])
