# Local GitOps mode on Docker Desktop

Bring the GitOps tier up on Docker Desktop's built-in Kubernetes to validate the platform manifests
without a GKE cluster, GPUs or Terraform.

## 1. What this covers

- Argo CD with the app-of-apps, and the applications it syncs: cert-manager, the KServe CRDs and
  controller (Standard mode), KEDA and the GPU config (namespaces, priority classes, quotas).
- Not covered: GPUs, the serving tier (`serving.enabled=false`), the Managed Prometheus scrape
  config (`monitoring.enabled=false`, its CRD exists only on GKE), and every benchmark number.
- Argo CD pulls from GitHub, so local mode validates the **pushed** branch, never the working tree.

## 2. Prerequisites

- Docker Desktop with Kubernetes enabled (Settings > Kubernetes) and at least 8 GB of memory for
  the Docker VM. The kube context is `docker-desktop` (override with `KUBE_CONTEXT=...`).
- `helm`, `kubectl` and `jq` on the PATH (`make tools` does not install `jq`; `brew install jq`).
- While the repository is private, a fine-grained GitHub token with read-only **Contents**
  permission on this repository, exported as `GIT_REPO_TOKEN`.

## 3. Bring-up

```bash
git push                                   # Argo CD syncs the remote branch
export GIT_REPO_TOKEN=<read-only token>    # private repo only
make local-up                              # Argo CD chart + root Application
make local-wait                            # polls until every Application is Synced and Healthy
```

`make local-up` uses the same Argo CD chart version, values file and bootstrap chart as the GKE
stage; only the two toggles differ. `make local-wait` ends with
`ready: 6/6 Applications Synced and Healthy` (about 3–5 minutes on first run, image pulls
included). It reads the repository URL and branch from `git remote`/`git rev-parse`; override with
`GIT_REPO_URL=...` or `GIT_REVISION=...`.

## 4. Inspect

```bash
make local-status
make argocd-ui KUBE_CONTEXT=docker-desktop   # admin password, then http://localhost:8080
```

Expected: six Applications (`platform-root`, `cert-manager`, `keda`, `kserve-crd`,
`kserve-resources`, `gpu-config`), all `Synced` and `Healthy`; pods `Running` in `argocd`,
`cert-manager`, `keda` and `kserve` (including `kserve-controller-manager`); the `inference` and
`bench` namespaces exist and are empty. `make gpu-smoke` does not apply here: there is no GPU node.

## 5. Tear down

```bash
make local-down
```

Uninstalls the bootstrap chart (the root Application's finalizer cascades to every child
Application and its resources), then Argo CD, then deletes the namespaces. The `docker-desktop`
context is otherwise untouched. The target is idempotent.

### Fallback: sync stuck at `Unknown`

Argo CD cannot read the repository. Check `GIT_REPO_TOKEN` (private repo) and that the branch
named by `make local-up` exists on GitHub, then rerun `make local-up`.

### Fallback: `local-down` times out

Rerun `make local-down`; both uninstalls tolerate a missing release. If an Application stays
behind, inspect it:

```bash
kubectl --context docker-desktop -n argocd get applications.argoproj.io <name> -o yaml
```

As a last resort remove its finalizer and rerun the teardown:

```bash
kubectl --context docker-desktop -n argocd patch application <name> --type merge -p '{"metadata":{"finalizers":[]}}'
```
