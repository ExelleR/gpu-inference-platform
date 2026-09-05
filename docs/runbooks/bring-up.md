# Bring-Up

Run everything from the repo root. This assumes `docs/runbooks/tools.md` is done and, if you want
a GPU pool on the first `make up`, that `docs/runbooks/quota-request.md` has already been granted.

## 1. Authenticate

```bash
gcloud auth login && gcloud auth application-default login
```

## 2. Bootstrap stage (once per billing account)

```bash
cp infra/terraform/bootstrap/terraform.tfvars.example infra/terraform/bootstrap/terraform.tfvars
# edit terraform.tfvars: project_id, billing_account, alert_email, monthly_budget_usd, ...
make bootstrap
```

This creates the GCP project (without the default VPC — the `gke` stage brings its own), enables
the required APIs, creates the Terraform state bucket, and sets the budget alert. It uses local
state and only runs once — leave it in place afterwards; the `gke` stage's backend depends on the
bucket it creates.

### Fallback: project creation via the API is refused

Create the project by hand in the Cloud Console, then add to `infra/terraform/bootstrap/main.tf`:

```hcl
import {
  to = google_project.this
  id = "projects/<project_id>"
}
```

Run `terraform apply` from `infra/terraform/bootstrap`, then delete the import block.

### Fallback: the budget fails with a quota-project error

Apply in two phases from `infra/terraform/bootstrap`:

```bash
terraform apply -target=google_project.this -target=google_project_service.apis -target=time_sleep.api_propagation
terraform apply
```

## 3. Configure the GKE stage

```bash
cp infra/terraform/gke/terraform.tfvars.example infra/terraform/gke/terraform.tfvars
```

Edit `terraform.tfvars` and set:

- `git_repo_url` — your fork of this repo, e.g. `https://github.com/<user>/gpu-inference-platform.git`
- `authorized_networks` — a list of `{ cidr, name }` objects that must include your machine's
  public IP. Find it with:

  ```bash
  curl -s https://ifconfig.me
  ```

  Append `/32` to the result to form a CIDR block and add it to the list, e.g.
  `authorized_networks = [{ cidr = "203.0.113.42/32", name = "laptop" }]`.

Optional GPU pools (`l4-timeslice` for `06-timeslice`, `a100-spot` for `08-a100-vs-l4`) are enabled
through `gpu_node_pools`; see `infra/terraform/gke/README.md` — the override replaces the whole
default map.

## 4. Bring the cluster up

```bash
make up                 # GPU pools stay at zero nodes until a benchmark Job needs one
make up SERVING=true    # also deploys the serving tier: baseline vLLM Deployment + KServe InferenceService
```

`SERVING=true` is only needed for `07-kserve-vs-raw` (its KServe target); it keeps two L4 nodes
running for as long as the cluster is up — see `docs/runbooks/cost-control.md`. Either form
provisions the VPC, NAT, GKE cluster, node pools and Argo CD (roughly 10-15 minutes) and ends by
printing a `gcloud container clusters get-credentials ...` command — run the printed command to
point `kubectl` at the new cluster, e.g.:

```bash
gcloud container clusters get-credentials gpu-inference --zone us-central1-a --project <project_id>
```

### Fallback: the first `make up` fails while planning the Helm releases

The helm provider is configured from the cluster's endpoint, which does not exist during the very
first plan. If `make up` stops there, apply the cluster on its own and then rerun `make up` (the
`terraform init` against the state bucket has already happened at that point; keep `SERVING=true`
on the rerun if you used it):

```bash
terraform -chdir=infra/terraform/gke apply -input=false -var="project_id=<project_id>" -target=google_container_cluster.this
make up
```

## 5. Watch Argo CD sync

```bash
make argocd-ui
```

Prints the `admin` password, then port-forwards `argocd-server` to `localhost:8080`. Open
`http://localhost:8080` and watch the `platform-root` application sync through its waves: the
`kserve-charts` OCI repository Secret (wave -3), cert-manager (wave -2), then the KServe CRDs and
KEDA (wave -1), then KServe resources, monitoring and GPU config (wave 0), and — only with
`SERVING=true` — the vLLM baseline and KServe serving apps (wave 1).

You can rehearse this sync locally first, without GPUs: `docs/runbooks/local.md`.

## 6. GPU smoke test

```bash
make gpu-smoke
```

Deletes a previous `gpu-smoke` Job first (Jobs are immutable, so a rerun needs a fresh one), then
applies the Job and waits for it. The first GPU node takes 3-6 minutes to scale up from zero. The
job prints the driver version via `/usr/local/nvidia/bin/nvidia-smi`; the log must show
`driver_version` >= 580.

## 7. Confirm the serving apps are up (only with `SERVING=true`)

```bash
kubectl -n inference get pods
```

Expect the baseline vLLM deployment pod and the KServe `InferenceService` predictor pod, both
`Running` (the first start downloads the model, which takes a few minutes). After a default
`make up` the `inference` namespace exists but is empty — skip this step.

With `OBSERVABILITY=true` as well, KEDA scales the predictor on queue depth; check the objects
KServe generated: `kubectl -n inference get scaledobject,hpa` (the HPA's target column reads the
queue-depth metric once the frontend answers; `<unknown>` means the frontend is not reachable).

## 8. Install the harness-deployed targets (experiments 06a, 06b and 07 only)

Platform experiments benchmark servers that `gpubench` does not deploy itself. Install them into
`bench` as releases of `platform/serving/vllm-chart` before running the experiment.

For `07-kserve-vs-raw` — the raw Deployment pinned to the vLLM `v0.24.0` that KServe 0.20 bundles
(the KServe side of the comparison is the serving tier, so this one needs `SERVING=true`):

```bash
helm upgrade --install vllm-raw-v024 platform/serving/vllm-chart -n bench -f platform/serving/vllm-chart/values-raw-v024.yaml
```

For the time-slicing pair, first enable the `l4-timeslice` pool (`enabled = true` in the
`gpu_node_pools` override, `infra/terraform/gke/README.md`) and rerun `make up`. The two releases
must run one at a time: three pods at 0.45 GPU-memory utilisation do not fit one 24 GB L4, and the
"single" measurement is only meaningful while it has the GPU to itself. So install one, run its
experiment, uninstall it, then the other:

```bash
helm upgrade --install vllm-single platform/serving/vllm-chart -n bench -f platform/serving/vllm-chart/values-timeslice-single.yaml
uv run --project bench gpubench run bench/experiments/06a-timeslice-single.yaml   # then collect + report
helm -n bench uninstall vllm-single
helm upgrade --install vllm-shared platform/serving/vllm-chart -n bench -f platform/serving/vllm-chart/values-timeslice-shared.yaml
uv run --project bench gpubench run bench/experiments/06b-timeslice-shared.yaml   # then collect + report
helm -n bench uninstall vllm-shared
```

Wait for the pods to be `Running` and ready (`kubectl -n bench get pods`) before `gpubench run`.
Uninstall the releases (`helm -n bench uninstall vllm-raw-v024`, etc.) once their results are
collected so the GPU nodes can scale back to zero.

## 9. Run the benchmark loop

```bash
uv run --project bench gpubench run bench/experiments/00-smoke.yaml
uv run --project bench gpubench collect bench/experiments/00-smoke.yaml -o results/$(date +%F)-smoke
uv run --project bench gpubench report results/<dir>
```

`run` deletes the experiment's previous Job and ConfigMap before applying, then polls each Job
until it completes; the wait (and the Job's own deadline) defaults to the experiment's `timeout_s`
— 4 hours unless the file overrides it, 8 hours for `04-batching`. `collect`'s reader pod
(`bench-reader`, namespace `bench`) is deleted automatically whether the copy succeeds or fails.
Finished Jobs are garbage-collected by `ttlSecondsAfterFinished` after 24 hours; `collect` does not
delete them.

## 10. Tear down

```bash
make down
```

Run this at the end of every session, **after** `gpubench collect`: `make down` destroys the
cluster together with the `bench-results` persistent disk behind the results PVC, so anything not
yet copied out is lost. See `docs/runbooks/cost-control.md` for exactly what it does and doesn't
remove.
