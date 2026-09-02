# Bootstrap Stage

## Purpose

Run once per billing account. Uses local state (gitignored) because the state bucket does not exist before this stage runs.

## Prerequisites

- `gcloud auth login && gcloud auth application-default login`
- Billing account upgraded from free trial
- The identity has Project Creator on the account (personal accounts create projects with no organization) and Billing Account Administrator (for the budget)

## Run

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
make bootstrap
```

## Fallback if project creation via API is refused

Create the project in the Cloud Console, then add to `main.tf`:

```hcl
import {
  to = google_project.this
  id = "projects/<project_id>"
}
```

Run `terraform apply`, then delete the import block.

## Fallback if the budget fails with a quota-project error

```bash
terraform apply -target=google_project.this -target=google_project_service.apis -target=time_sleep.api_propagation
terraform apply
```
