# Observability: Managed Prometheus frontend and Grafana

Opt-in, GKE only. Adds a query frontend for Managed Prometheus and a Grafana with the vLLM
dashboard; the same frontend is the Prometheus API that KEDA autoscaling queries.

## 1. What it deploys

- `platform/observability`: a `frontend` Deployment (`gke.gcr.io/prometheus-engine/frontend`)
  serving the Prometheus HTTP API on `frontend.observability.svc:9090`, its Kubernetes service
  account bound through Workload Identity to a Google service account with
  `roles/monitoring.viewer` (created by Terraform), and the dashboard ConfigMap.
- Grafana (chart 13.2.1) with a provisioned Prometheus datasource pointing at that frontend and
  the dashboard sidecar. No admin password is committed; the chart generates one.

## 2. Bring-up

```bash
make up SERVING=true OBSERVABILITY=true   # serving tier gives the dashboard something to show
make grafana-ui KUBE_CONTEXT=<your gke context or empty for current>
```

`make grafana-ui` prints the `admin` password and forwards Grafana to http://localhost:3000. Open
the "vLLM serving" dashboard: requests running and waiting, KV cache usage, TTFT and inter-token
latency percentiles, output tokens per second, preemptions; the `namespace` variable filters by
namespace (`inference` for the serving tier, `bench` for harness-deployed variants).

## 3. Check the frontend directly

```bash
kubectl -n observability port-forward svc/frontend 9090
curl -s 'http://localhost:9090/api/v1/query?query=vllm:num_requests_waiting' | head -c 300
```

An empty result set with a running vLLM pod means Managed Prometheus is not scraping it; check
`kubectl -n gpu-system get clusterpodmonitoring` and the pod's `app.kubernetes.io/component: vllm`
label. A 403 means the Workload Identity binding is missing (`terraform apply` with
`observability_enabled = true` creates it).

## 4. Tear down

`make down OBSERVABILITY=true` removes the Google service account with the cluster; with
`OBSERVABILITY=false` Argo CD prunes the two Applications and their namespace at the next sync.

### Fallback: dashboard shows "No data"

The vLLM metric names are the vLLM 0.28 V1 names (`docs/methodology.md`, "Server-side metrics").
If a later vLLM renames them, edit `platform/observability/dashboards/vllm.json` and push; the
sidecar reloads the ConfigMap within a minute.
