from pathlib import Path

import pytest
from pydantic import ValidationError

from gpubench.config import Experiment, load_experiment

ENGINE = """
name: baseline-l4
kind: engine
gpu_pool: l4-spot
accelerator: nvidia-l4
variants:
  - name: fp8-defaults
    model: Qwen/Qwen3-8B-FP8
    server_args: ["--max-model-len", "8192"]
loads:
  - {max_concurrency: 1, num_prompts: 50}
  - {max_concurrency: 16, num_prompts: 200}
"""


def test_engine_experiment_loads_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "e.yaml"
    path.write_text(ENGINE)
    exp = load_experiment(path)
    assert exp.kind == "engine"
    assert exp.variants[0].server_args == ["--max-model-len", "8192"]
    assert exp.num_runs == 3 and exp.seed == 0 and exp.percentiles == [50, 90, 99]
    assert exp.dataset.name == "sharegpt"
    assert exp.loads[1].max_concurrency == 16


def test_platform_experiment_requires_targets() -> None:
    data = {"name": "x", "kind": "platform", "loads": [{"max_concurrency": 1}]}
    with pytest.raises(ValidationError, match="targets"):
        Experiment.model_validate(data)


def test_engine_experiment_rejects_targets() -> None:
    data = {
        "name": "x",
        "kind": "engine",
        "variants": [{"name": "v"}],
        "targets": [{"name": "t", "url": "http://a", "model": "m", "served_model": "m"}],
        "loads": [{"max_concurrency": 1}],
    }
    with pytest.raises(ValidationError, match="targets"):
        Experiment.model_validate(data)


def test_name_must_be_slug() -> None:
    with pytest.raises(ValidationError, match="name"):
        Experiment.model_validate(
            {
                "name": "Bad Name",
                "kind": "engine",
                "variants": [{"name": "v"}],
                "loads": [{"max_concurrency": 1}],
            }
        )


def test_server_sweep_expands_to_cartesian_product() -> None:
    exp = Experiment.model_validate(
        {
            "name": "batching",
            "kind": "engine",
            "variants": [
                {
                    "name": "grid",
                    "server_sweep": {
                        "max-num-seqs": [64, 128],
                        "max-num-batched-tokens": [2048, 4096],
                    },
                }
            ],
            "loads": [{"max_concurrency": 16}],
        }
    )
    combos = exp.variants[0].sweep_combinations()
    assert len(combos) == 4
    assert {"max-num-seqs": 64, "max-num-batched-tokens": 4096} in combos


def test_node_selector_and_timeout_defaults_and_bounds() -> None:
    base = {
        "name": "x",
        "kind": "engine",
        "variants": [{"name": "v"}],
        "loads": [{"max_concurrency": 1}],
    }
    exp = Experiment.model_validate(base)
    assert exp.node_selector == {} and exp.timeout_s == 14400
    exp = Experiment.model_validate(
        {**base, "node_selector": {"pool": "a100-spot"}, "timeout_s": 28800}
    )
    assert exp.node_selector == {"pool": "a100-spot"} and exp.timeout_s == 28800
    with pytest.raises(ValidationError, match="timeout_s"):
        Experiment.model_validate({**base, "timeout_s": 599})
