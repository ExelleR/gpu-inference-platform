variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "cluster_name" {
  type    = string
  default = "gpu-inference"
}

variable "authorized_networks" {
  description = "CIDRs allowed to reach the control plane. Must include the machine running terraform apply."
  type = list(object({
    cidr = string
    name = string
  }))
}

variable "system_machine_type" {
  type    = string
  default = "e2-standard-2"
}

variable "system_min_nodes" {
  type    = number
  default = 1
}

variable "system_max_nodes" {
  type    = number
  default = 3
}

variable "gpu_node_pools" {
  description = "GPU node pools. Each scales 0..max_nodes. Changing accelerator settings replaces the pool."
  type = map(object({
    machine_type      = string
    accelerator_type  = string
    accelerator_count = optional(number, 1)
    spot              = optional(bool, true)
    max_nodes         = optional(number, 1)
    partition_size    = optional(string)
    sharing = optional(object({
      strategy = string
      clients  = number
    }))
    driver_version = optional(string, "LATEST")
    enabled        = optional(bool, true)
  }))
  default = {
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
      enabled          = false
    }
    a100-mig = {
      machine_type     = "a2-highgpu-1g"
      accelerator_type = "nvidia-tesla-a100"
      partition_size   = "3g.20gb"
      enabled          = false
    }
  }
}

variable "serving_enabled" {
  description = "Deploy the serving tier (baseline vLLM Deployment and KServe InferenceService) via Argo CD. Keeps two L4 nodes running while the cluster is up."
  type        = bool
  default     = false
}

variable "argocd_chart_version" {
  type    = string
  default = "10.6.0"
}

variable "git_repo_url" {
  description = "Git URL Argo CD syncs from, e.g. https://github.com/<user>/gpu-inference-platform.git"
  type        = string
}

variable "git_revision" {
  type    = string
  default = "main"
}

variable "git_repo_token" {
  description = "Token for a private repo. Leave empty for a public repo."
  type        = string
  sensitive   = true
  default     = ""
}

variable "argocd_apps_path" {
  type    = string
  default = "platform/argocd/apps"
}

variable "observability_enabled" {
  description = "Deploy the Managed Prometheus query frontend and Grafana (make up OBSERVABILITY=true)."
  type        = bool
  default     = false
}
