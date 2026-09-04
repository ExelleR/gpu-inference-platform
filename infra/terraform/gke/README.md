# GKE Stage

## Purpose

This stage provisions a GKE cluster with Argo CD as the GitOps engine. It is applied at the start of a work session with `make up` and destroyed at the end with `make down`; the bootstrap stage (`make bootstrap`, run once per billing account) must already exist, because this stage's Terraform state lives in the bootstrap bucket under the `gke` prefix.

## Required Variables

The following variables must be set in `terraform.tfvars`:

- `project_id`: The GCP project ID (`make up` also passes it from the bootstrap stage's output)
- `git_repo_url`: The Git repository URL that Argo CD syncs from (e.g., `https://github.com/<user>/gpu-inference-platform.git`)
- `authorized_networks`: A list of `{ cidr, name }` objects allowed to reach the control plane. Must include your machine's public IP. To find your IP, run:
  ```
  curl -s https://ifconfig.me
  ```
  Then add `/32` to create a CIDR block and give the entry a name:
  ```hcl
  authorized_networks = [
    { cidr = "203.0.113.42/32", name = "laptop" },
  ]
  ```

## Optional Variables

- `serving_enabled` (bool, default `false`): deploys the serving tier — the baseline vLLM Deployment and the KServe `InferenceService` — through Argo CD, by passing `serving.enabled` to the bootstrap chart. `make up SERVING=true` sets it. While enabled it keeps two L4 nodes running for as long as the cluster is up (see `docs/runbooks/cost-control.md`); the default leaves every GPU pool at zero nodes until a benchmark Job needs one.
- `gpu_node_pools`: the GPU pools, described below.

## GPU Pools

The defaults in `variables.tf` are `l4-spot` (enabled, up to 3 nodes), `l4-timeslice` (disabled), `a100-spot` (disabled) and `a100-mig` (disabled). Every pool scales from zero.

Overriding `gpu_node_pools` in `terraform.tfvars` **replaces the whole default map** — Terraform does not merge a map variable with its default — so any pool you leave out of the override is removed. Copy the full map and change only what you need. Enabling the spot A100 pool (for `bench/experiments/08-a100-vs-l4.yaml`) while keeping the defaults looks like this:

```hcl
gpu_node_pools = {
  l4-spot = {
    machine_type     = "g2-standard-4"
    accelerator_type = "nvidia-l4"
    max_nodes        = 3
  }
  l4-timeslice = {
    machine_type     = "g2-standard-4"
    accelerator_type = "nvidia-l4"
    sharing = {
      strategy = "TIME_SHARING"
      clients  = 4
    }
    enabled = false
  }
  a100-spot = {
    machine_type     = "a2-highgpu-1g"
    accelerator_type = "nvidia-tesla-a100"
    enabled          = true
  }
  a100-mig = {
    machine_type     = "a2-highgpu-1g"
    accelerator_type = "nvidia-tesla-a100"
    partition_size   = "3g.20gb"
    enabled          = false
  }
}
```

Set `enabled = true` on `l4-timeslice` the same way for `bench/experiments/06-timeslice.yaml`. Spot A100 pools need their own quota (`docs/runbooks/quota-request.md`).

## Pool Replacement Note

Changing accelerator settings (e.g., `accelerator_type` or `partition_size`) replaces the node pool, which causes downtime for workloads on that pool.

## Bring-Up Time

The cluster and Argo CD bootstrap typically take about 10–15 minutes to complete. If the very first `make up` fails while planning the Helm releases — the helm provider needs the cluster endpoint, which does not exist yet — apply the cluster on its own and then rerun `make up`:

```bash
terraform -chdir=infra/terraform/gke apply -input=false -var="project_id=<project_id>" -target=google_container_cluster.this
make up
```

## GPU Driver Check

After the first GPU node appears, verify the driver is installed and running:

```
kubectl get nodes -l gpu -o custom-columns=NAME:.metadata.name,DRIVER:.metadata.labels.cloud\.google\.com/gke-gpu-driver-version
```
