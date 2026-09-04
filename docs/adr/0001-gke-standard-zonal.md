# GKE Standard mode, zonal cluster in us-central1-a

Status: accepted
Date: 2026-09-01

## Context

The platform needs one GKE cluster to host both GPU inference workloads and the benchmark harness, provisioned and torn down repeatedly across work sessions (see ADR 0002). Two cluster modes are available: Autopilot and Standard. Autopilot has grown real GPU support — it now supports GPU node pools, MIG partitioning, and Spot capacity — but it manages node pools internally and does not expose them as separate, inspectable objects. This repository's node pools (`l4-spot`, `l4-timeslice`, `a100-spot`, `a100-mig`, see `infra/terraform/gke/nodepools.tf`) need to be declared, toggled, and inspected individually. A regional vs. zonal control plane, and a release channel, also had to be picked.

## Decision

Run GKE **Standard** mode, **zonal** in `us-central1-a`, on the **Regular** release channel. Standard keeps node pools first-class and visible: taints, MIG partition size, GPU time-slicing, and scale-to-zero (`total_min_node_count = 0`) are all pool-level fields the harness and operators can read and reason about, which Autopilot would hide behind its own scheduler. GPU driver and device plugin installation is fully GKE-managed as of GKE `1.32.2-gke.1297000`, so no NVIDIA GPU Operator or driver DaemonSet is deployed — `gpu_driver_installation_config` on each node pool is enough. Networking uses Dataplane V2 (`datapath_provider = "ADVANCED_DATAPATH"`), and nodes are private with egress through Cloud NAT.

## Consequences

GCP's free tier covers the $0.10/hour zonal cluster management fee for one zonal cluster per billing account, so the cluster shape itself is free; the real cost drivers are node and NAT usage while the cluster is up. Zonal placement means a single-zone outage takes the cluster down entirely — acceptable for a benchmark/demo platform, not for production HA. Standard mode also means node pool sizing, taints, and tolerations are the operator's responsibility rather than Autopilot's, which is intentional here since the benchmark harness schedules directly against pool labels and node selectors.
