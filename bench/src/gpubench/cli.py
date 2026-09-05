"""gpubench command line."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from gpubench.collect import collect as collect_results
from gpubench.config import load_experiment
from gpubench.k8s import Kubectl
from gpubench.render import NAMESPACE, dump_manifests, job_names, render_experiment
from gpubench.report import write_summary

app = typer.Typer(help="Run in-cluster vLLM benchmarks and compute cost per million tokens.")
# The Job's own activeDeadlineSeconds is the real budget; the client waits a little longer so a
# Failed condition (DeadlineExceeded) surfaces instead of a client-side TimeoutError.
WAIT_GRACE_S = 300
DEFAULT_PRICES = Path(__file__).resolve().parents[2] / "prices.yaml"


@app.command()
def validate(paths: list[Path]) -> None:
    """Validate experiment YAML files."""
    failed = False
    for path in paths:
        try:
            exp = load_experiment(path)
            typer.echo(f"ok   {path} ({exp.kind}, {len(exp.loads)} load levels)")
        except (ValidationError, ValueError, OSError, yaml.YAMLError) as exc:
            failed = True
            typer.echo(f"FAIL {path}: {exc}")
    raise typer.Exit(code=1 if failed else 0)


@app.command()
def render(paths: list[Path], out: Path = typer.Option(..., "-o", "--out")) -> None:
    """Render Kubernetes manifests for experiments into OUT/<name>.yaml."""
    for path in paths:
        exp = load_experiment(path)
        dump_manifests(render_experiment(exp), out / f"{exp.name}.yaml")
        typer.echo(f"rendered {out / (exp.name + '.yaml')}")


@app.command()
def run(
    path: Path,
    timeout_s: int | None = typer.Option(
        None, help="Per-Job wait timeout in seconds (default: the experiment's timeout_s)"
    ),
) -> None:
    """Remove a previous run's Jobs, apply the PVC, ConfigMaps and Jobs, then wait for each Job."""
    exp = load_experiment(path)
    kube = Kubectl()
    wait_timeout = exp.timeout_s if timeout_s is None else timeout_s
    for name in job_names(exp):
        kube.delete("job", name, NAMESPACE)
        kube.delete("configmap", name, NAMESPACE)
    kube.apply(render_experiment(exp))
    for name in job_names(exp):
        typer.echo(f"waiting for job/{name} in {NAMESPACE} ...")
        kube.wait_job(name, NAMESPACE, timeout_s=wait_timeout + WAIT_GRACE_S)
    typer.echo("all jobs complete; next: gpubench collect")


@app.command()
def collect(
    path: Path,
    out: Path = typer.Option(..., "-o", "--out", help="e.g. results/2026-11-01-baseline-l4"),
    prices: Path = typer.Option(DEFAULT_PRICES),
) -> None:
    """Copy results from the PVC into OUT/raw and write OUT/manifest.json."""
    exp = load_experiment(path)
    collect_results(exp, out, prices, Kubectl())
    typer.echo(f"collected into {out}")


@app.command()
def report(results_dir: Path, prices: Path = typer.Option(DEFAULT_PRICES)) -> None:
    """Write summary.md and charts/ for a collected results directory."""
    typer.echo(f"wrote {write_summary(results_dir, prices)}")
