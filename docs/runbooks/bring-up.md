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

This creates the GCP project, enables the required APIs, creates the Terraform state bucket, and
sets the budget alert. It uses local state and only runs once — leave it in place afterwards; the
`gke` stage's backend depends on the bucket it creates.

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
- `authorized_networks` — must include your machine's public IP. Find it with:

  ```bash
  curl -s https://ifconfig.me
  ```

  Append `/32` to the result to form a CIDR block (e.g. `203.0.113.42/32`) and add it to the
  `authorized_networks` list.

## 4. Bring the cluster up

```bash
make up
```

Provisions the VPC, NAT, GKE cluster, node pools and Argo CD (roughly 10-15 minutes). At the end
it prints a `gcloud container clusters get-credentials ...` command — run the printed command to
point `kubectl` at the new cluster, e.g.:

```bash
gcloud container clusters get-credentials gpu-inference --zone us-central1-a --project <project_id>
```

## 5. Watch Argo CD sync

```bash
make argocd-ui
```

Prints the `admin` password, then port-forwards `argocd-server` to `localhost:8080`. Open
`http://localhost:8080` and watch the `platform-root` application sync through its waves:
cert-manager (wave -2), then the KServe CRDs and KEDA (wave -1), then KServe resources,
monitoring and GPU config (wave 0), then the vLLM baseline and KServe serving apps (wave 1).

## 6. GPU smoke test

```bash
make gpu-smoke
```

The first GPU node takes 3-6 minutes to scale up from zero. The job prints the driver version via
`/usr/local/nvidia/bin/nvidia-smi`; the log must show `driver_version` >= 580.

## 7. Confirm the serving apps are up

```bash
kubectl -n inference get pods
```

Expect the baseline vLLM deployment pod and the KServe `InferenceService` predictor pod, both
`Running`.

## 8. Run the benchmark loop

```bash
uv run --project bench gpubench run bench/experiments/00-smoke.yaml
uv run --project bench gpubench collect bench/experiments/00-smoke.yaml -o results/$(date +%F)-smoke
uv run --project bench gpubench report results/<dir>
```

`collect`'s reader pod (`bench-reader`, namespace `bench`) is deleted automatically whether the
copy succeeds or fails.

## 9. Tear down

```bash
make down
```

Run this at the end of every session. See `docs/runbooks/cost-control.md` for exactly what it
does and doesn't remove.
