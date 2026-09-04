"""Parse `vllm bench serve --save-result` JSON files into typed results."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

PERCENTILE_KEY = re.compile(r"^p(\d+)_(ttft|tpot|itl|e2el)_ms$")
STAT_KEY = re.compile(r"^(mean|median|std)_(ttft|tpot|itl|e2el)_ms$")
RAW_ARRAY_KEYS = {
    "input_lens",
    "output_lens",
    "ttfts",
    "itls",
    "start_times",
    "generated_texts",
    "errors",
}
SCALAR_KEYS = {
    "date",
    "backend",
    "model_id",
    "tokenizer_id",
    "num_prompts",
    "request_rate",
    "burstiness",
    "max_concurrency",
    "duration",
    "completed",
    "failed",
    "total_input_tokens",
    "total_output_tokens",
    "request_throughput",
    "request_goodput",
    "output_throughput",
    "total_token_throughput",
    "max_output_tokens_per_s",
    "max_concurrent_requests",
    "rtfx",
}


class LatencyStats(BaseModel):
    mean_ms: float
    median_ms: float
    std_ms: float | None = None
    percentiles_ms: dict[int, float] = Field(default_factory=dict)

    def p(self, q: int) -> float:
        return self.percentiles_ms[q]


class RunResult(BaseModel):
    model_id: str
    backend: str = "openai"
    date: str = ""
    num_prompts: int
    max_concurrency: int | None = None
    request_rate: float = math.inf
    duration_s: float
    completed: int
    failed: int = 0
    total_input_tokens: int
    total_output_tokens: int
    request_throughput: float
    output_throughput: float
    total_token_throughput: float
    request_goodput: float | None = None
    ttft: LatencyStats
    tpot: LatencyStats
    itl: LatencyStats
    e2el: LatencyStats | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("request_rate", mode="before")
    @classmethod
    def _inf_strings(cls, value: object) -> object:
        if isinstance(value, str) and value.lower() in {"inf", "infinity"}:
            return math.inf
        return value

    @property
    def error_rate(self) -> float:
        total = self.completed + self.failed
        return self.failed / total if total else 0.0


def _latency(data: dict, metric: str) -> LatencyStats | None:
    if f"mean_{metric}_ms" not in data:
        return None
    percentiles = {
        int(match.group(1)): float(value)
        for key, value in data.items()
        if (match := PERCENTILE_KEY.match(key)) and match.group(2) == metric
    }
    return LatencyStats(
        mean_ms=data[f"mean_{metric}_ms"],
        median_ms=data[f"median_{metric}_ms"],
        std_ms=data.get(f"std_{metric}_ms"),
        percentiles_ms=percentiles,
    )


def parse_result(data: dict) -> RunResult:
    metadata = {
        key: str(value)
        for key, value in data.items()
        if key not in SCALAR_KEYS
        and key not in RAW_ARRAY_KEYS
        and not key.startswith("_")
        and not PERCENTILE_KEY.match(key)
        and not STAT_KEY.match(key)
    }
    return RunResult(
        model_id=data["model_id"],
        backend=data.get("backend", "openai"),
        date=data.get("date", ""),
        num_prompts=data["num_prompts"],
        max_concurrency=data.get("max_concurrency"),
        request_rate=data.get("request_rate", math.inf),
        duration_s=data["duration"],
        completed=data["completed"],
        failed=data.get("failed", 0),
        total_input_tokens=data["total_input_tokens"],
        total_output_tokens=data["total_output_tokens"],
        request_throughput=data["request_throughput"],
        output_throughput=data["output_throughput"],
        total_token_throughput=data["total_token_throughput"],
        request_goodput=data.get("request_goodput"),
        ttft=_latency(data, "ttft"),
        tpot=_latency(data, "tpot"),
        itl=_latency(data, "itl"),
        e2el=_latency(data, "e2el"),
        metadata=metadata,
    )


def load_result(path: Path) -> RunResult:
    return parse_result(json.loads(path.read_text()))


SKIPPED_FILES = {"manifest.json", "summary.json"}
REQUIRED_KEYS = {"model_id", "output_throughput"}


def load_results(root: Path) -> list[RunResult]:
    """Load every benchmark result under root, recording each file's root-relative path.

    Skips manifest.json, the per-combination summary.json that `vllm bench sweep serve` writes
    (a JSON list of the runs, not a result) and any JSON without the benchmark fields.
    """
    results = []
    for path in sorted(root.rglob("*.json")):
        if path.name in SKIPPED_FILES:
            continue
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not REQUIRED_KEYS <= data.keys():
            continue
        result = parse_result(data)
        result.metadata["path"] = path.relative_to(root).as_posix()
        results.append(result)
    return results
