# Ephemeral GKE cluster with a persistent bootstrap stage and a $100 budget alert

Status: accepted
Date: 2026-09-01

## Context

This is a personal, cost-bounded project, not a production service: GPU nodes dominate the bill, and nothing requires the cluster to exist between work sessions. Terraform is split into two stages — `infra/terraform/bootstrap` (GCP project, APIs, the Terraform state bucket, the budget) and `infra/terraform/gke` (VPC, NAT, cluster, node pools, Argo CD) — and the Makefile exposes the second stage as `make up` / `make down`.

## Decision

The GKE stage is fully ephemeral: `make up` applies it at the start of a work session, `make down` destroys it at the end. By default `make up` leaves every GPU pool at zero nodes; `make up SERVING=true` additionally deploys the serving tier (the baseline vLLM Deployment and the KServe `InferenceService`), whose two L4 nodes then run for the whole session. `deletion_protection = false` keeps `terraform destroy` unblocked, and `cluster_autoscaling { autoscaling_profile = "OPTIMIZE_UTILIZATION" }` reclaims idle nodes aggressively while the cluster is up. Every GPU pool also sets `total_min_node_count = 0`, so GPU capacity scales to zero even before a `make down`. The bootstrap stage is applied once and left in place, since it holds the state bucket the GKE stage's backend depends on. `infra/terraform/bootstrap/budget.tf` sets a $100/month billing budget with alerts at 50%, 90%, and 100% of spend (plus 100%-of-forecast), emailed via a monitoring notification channel.

Keeping this lifecycle reliable on a contributor's machine matters too: GNU Make only honors `.SHELLFLAGS` (which sets `pipefail`) from version 3.82 onward, but macOS ships GNU Make 3.81. The Makefile's pipeline recipes (`tools`, `schemas`) therefore also call `set -o pipefail;` explicitly, so a failing `curl` or `helm template` upstream of a pipe still fails the recipe on a stock macOS toolchain.

## Consequences

Idle cost between sessions is effectively zero: once the cluster is destroyed, only the bootstrap stage's state bucket and budget remain, both negligible. Cloud NAT bills roughly $0.044/hour, only while the GKE stage is up. Bring-up (`make up`, cluster plus Argo CD bootstrap) takes about 10–15 minutes — the price of ephemerality. Destroying and recreating the cluster each session also means anything not declared in Terraform or synced by Argo CD is lost on `make down`, part of why the harness commits its results to git instead of relying on in-cluster state.
