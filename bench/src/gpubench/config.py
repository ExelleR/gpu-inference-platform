"""Experiment definitions loaded from bench/experiments/*.yaml."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

DEFAULT_IMAGE = "vllm/vllm-openai:v0.28.0"
SLUG = r"^[a-z0-9][a-z0-9-]*$"


class Dataset(BaseModel):
    name: Literal["sharegpt", "random"] = "sharegpt"
    url: str = (
        "https://huggingface.co/datasets/anon8231489123/ShareGPT_Vicuna_unfiltered/"
        "resolve/main/ShareGPT_V3_unfiltered_cleaned_split.json"
    )
    sha256: str | None = None
    random_input_len: int = 1024
    random_output_len: int = 128
    random_range_ratio: float = 0.5


class LoadLevel(BaseModel):
    max_concurrency: int = Field(ge=1)
    num_prompts: int = Field(default=200, ge=1)
    request_rate: float | None = None


class Variant(BaseModel):
    """A server configuration for an engine experiment."""

    name: str = Field(pattern=SLUG)
    model: str = "Qwen/Qwen3-8B-FP8"
    served_name: str = "qwen3-8b"
    image: str = DEFAULT_IMAGE
    server_args: list[str] = Field(default_factory=list)
    server_sweep: dict[str, list[int | float | str]] = Field(default_factory=dict)

    def sweep_combinations(self) -> list[dict[str, int | float | str]]:
        if not self.server_sweep:
            return [{}]
        keys = list(self.server_sweep)
        return [
            dict(zip(keys, values, strict=True))
            for values in itertools.product(*self.server_sweep.values())
        ]


class Target(BaseModel):
    """An already-running server for a platform experiment."""

    name: str = Field(pattern=SLUG)
    url: str
    model: str
    served_model: str


class Experiment(BaseModel):
    name: str = Field(pattern=SLUG)
    kind: Literal["engine", "platform"]
    gpu_pool: str = "l4-spot"
    accelerator: str = "nvidia-l4"
    client_image: str = DEFAULT_IMAGE
    variants: list[Variant] = Field(default_factory=list)
    targets: list[Target] = Field(default_factory=list)
    loads: list[LoadLevel] = Field(min_length=1)
    dataset: Dataset = Field(default_factory=Dataset)
    num_runs: int = Field(default=3, ge=1)
    seed: int = 0
    percentiles: list[int] = Field(default_factory=lambda: [50, 90, 99])
    goodput: dict[str, float] = Field(default_factory=lambda: {"ttft": 500.0, "tpot": 50.0})

    @model_validator(mode="after")
    def _check_kind(self) -> Experiment:
        if self.kind == "engine":
            if not self.variants:
                raise ValueError("engine experiments need at least one entry in variants")
            if self.targets:
                raise ValueError("engine experiments must not define targets")
        else:
            if not self.targets:
                raise ValueError("platform experiments need at least one entry in targets")
            if self.variants:
                raise ValueError("platform experiments must not define variants")
        return self


def load_experiment(path: Path) -> Experiment:
    with path.open() as handle:
        return Experiment.model_validate(yaml.safe_load(handle))
