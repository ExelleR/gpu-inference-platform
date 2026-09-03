# Tools

What to install and verify on your own machine before touching any cloud stage. Nothing in this
file talks to GCP.

## Verified local state

This repo is developed and validated against:

| Tool | Version | Check |
| --- | --- | --- |
| terraform | 1.5.7 | `terraform version` |
| kubectl | 1.37 | `kubectl version --client` |
| helm | 4.2.4 | `helm version` |
| python | 3.14 | `python3 --version` |
| uv | any recent | `uv --version` |
| docker | any recent | `docker --version` |
| git | any recent | `git --version` |

Terraform 1.5.7 is the last MPL-licensed release (1.6.0 and later moved to BUSL). Both
`infra/terraform/bootstrap` and `infra/terraform/gke` pin `required_version >= 1.5.7`, and the
code stays compatible with it. [OpenTofu](https://opentofu.org) >= 1.6 is a drop-in alternative if
you'd rather stay on an OSS license end to end — `alias terraform=tofu` and every `make` target
that shells out to `terraform` keeps working unchanged.

## Install

```bash
brew install --cask google-cloud-sdk
gcloud components install gke-gcloud-auth-plugin
brew install gh tflint yq
make tools          # kubeconform into .tools/bin, uv sync for bench
uvx pre-commit install
```

- `make tools` downloads `kubeconform` into `.tools/bin` and runs `uv sync --project bench`
  (creates `bench/.venv`).
- `tflint` mirrors the `tflint` step in `.github/workflows/ci.yaml` — it isn't wired into any
  `make` target, so run it directly when you touch Terraform:
  ```bash
  tflint --init
  tflint --chdir=infra/terraform/bootstrap
  tflint --chdir=infra/terraform/gke
  ```
- `gh` and `yq` are general-purpose GitHub CLI / YAML CLI helpers (PRs, poking at the YAML under
  `platform/` and `infra/`). Like `tflint`, neither is invoked by a `make` target.
- None of `gh`, `tflint` or `yq` are required for the cloud stages themselves
  (`make bootstrap` / `make up` / `make down`).

## Generating CRD schemas (optional, needs network)

```bash
make schemas
```

Fetches the KServe, KEDA and Google Managed Prometheus CRDs and converts them into JSON Schemas
under `.tools/schemas`, so `make kubeconform` can validate custom resources —
`InferenceService`, `ClusterPodMonitoring`, etc. — strictly instead of skipping them. Only needed
if you're changing manifests under `platform/`; not required for a plain bring-up.

## Make on macOS

macOS ships GNU Make 3.81, which predates `.SHELLFLAGS` support (added in 3.82) and silently
ignores it. The Makefile therefore sets `set -o pipefail` explicitly inside every recipe that
pipes commands together (`tools`, `schemas`), so a failing `curl` or `helm template` upstream of a
pipe still fails the recipe even on the stock toolchain.

For `-e -o pipefail` semantics on *every* recipe, not just the piped ones, install GNU Make 4.x:

```bash
brew install make
```

Homebrew installs it as `gmake` (the formula is keg-only, so it never overwrites
`/usr/bin/make`). Either run `gmake <target>` directly, or put
`$(brew --prefix make)/libexec/gnubin` ahead of `/usr/bin` in `PATH` so plain `make` resolves to
GNU Make 4.x.

## Next

`docs/runbooks/quota-request.md`, then `docs/runbooks/bring-up.md`.
