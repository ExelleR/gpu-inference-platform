# Cost Control

## What costs money while the cluster is up

- **System node pool** (`system`, `e2-standard-2`, `system_min_nodes = 1` by default) — always
  running while the `gke` stage exists, regardless of workload.
- **Cloud NAT** (`google_compute_router_nat` in `infra/terraform/gke/network.tf`) — a flat
  per-hour charge (roughly $0.044/hour, see `docs/adr/0002-ephemeral-cluster-and-budget.md`) plus
  egress, for as long as the cluster is up.
- **GPU node(s)** — only while at least one GPU pod is scheduled. Every pool in `gpu_node_pools`
  sets `total_min_node_count = 0`, so an idle GPU pool costs nothing.
- **Managed Prometheus ingestion** — `monitoring_config.managed_prometheus.enabled = true` on the
  cluster (`infra/terraform/gke/cluster.tf`); billed on sample volume from whatever
  `ClusterPodMonitoring` targets are being scraped (DCGM GPU metrics included).

## What costs money while the cluster is down

- The bootstrap stage's Terraform state bucket (`<project_id>-tfstate`) — versioned, capped at the
  10 newest versions of a handful of small state files. A few cents a month.
- Nothing else. `make down` destroys the VPC, NAT, cluster and node pools; the bootstrap stage
  (project, APIs, state bucket, budget) is left in place on purpose.

## Budget alert

`infra/terraform/bootstrap/budget.tf` creates a billing budget (`monthly_budget_usd`, default
`$100`) with alert emails at:

- 50% of actual spend
- 90% of actual spend
- 100% of actual spend
- 100% of forecasted spend

sent to `alert_email` from `terraform.tfvars`. Check current spend against it:

```bash
gcloud billing projects describe <project_id>
```

## GPU nodes scale down on their own

`infra/terraform/gke/cluster.tf` sets `cluster_autoscaling { autoscaling_profile =
"OPTIMIZE_UTILIZATION" }`. Combined with `total_min_node_count = 0` on every GPU pool: **no GPU
pod → the GPU node disappears within roughly 10 minutes**, with no action needed between
benchmark runs. You still need to run `make down` deliberately at the end of a session, since the
system pool and NAT never scale to zero on their own.

## Verify nothing is left running

```bash
gcloud compute instances list --project <project_id>
```

Expect an empty list once `make down` has finished.

## Monthly envelope (L4 spot)

`bench/prices.yaml` prices the default pool, `l4-spot` (`g2-standard-4` with one `nvidia-l4`,
spot, `us-central1`), as a whole VM at $0.424/hour
(see `docs/adr/0003-l4-default-a100-opt-in.md`):

| Budget | L4 spot hours |
| --- | --- |
| $50  | ~118 hours |
| $100 | ~236 hours |

This is GPU node time only — it ignores the system pool and NAT, which run whenever the cluster
is up regardless of GPU usage (see above).
