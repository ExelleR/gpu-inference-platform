# GKE Stage

## Purpose

This stage provisions a GKE cluster with Argo CD as the GitOps engine. The cluster is applied per work session and destroyed with `make down`. Terraform state is stored in the bootstrap bucket under the `gke` prefix.

## Required Variables

The following variables must be set in `terraform.tfvars`:

- `project_id`: The GCP project ID
- `git_repo_url`: The Git repository URL that Argo CD syncs from (e.g., `https://github.com/<user>/gpu-inference-platform.git`)
- `authorized_networks`: A list of CIDR blocks allowed to reach the control plane. Must include your machine's public IP. To find your IP, run:
  ```
  curl -s https://ifconfig.me
  ```
  Then add `/32` to create a CIDR block (e.g., `203.0.113.42/32`).

## Enabling a GPU Pool

To enable a GPU node pool, override the `gpu_node_pools` variable in `terraform.tfvars`. For example:

```hcl
gpu_node_pools = {
  a100-mig = {
    machine_type     = "a2-highgpu-1g"
    accelerator_type = "nvidia-tesla-a100"
    partition_size   = "3g.20gb"
  }
}
```

## Pool Replacement Note

Changing accelerator settings (e.g., `accelerator_type` or `partition_size`) replaces the node pool, which causes downtime for workloads on that pool.

## Bring-Up Time

The cluster and Argo CD bootstrap typically take about 10–15 minutes to complete.

## GPU Driver Check

After the first GPU node appears, verify the driver is installed and running:

```
kubectl get nodes -l gpu -o custom-columns=NAME:.metadata.name,DRIVER:.metadata.labels.cloud\.google\.com/gke-gpu-driver-version
```
