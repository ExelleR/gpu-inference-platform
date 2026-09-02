locals {
  gpu_pools = { for name, pool in var.gpu_node_pools : name => pool if pool.enabled }
}

resource "google_container_node_pool" "system" {
  name     = "system"
  cluster  = google_container_cluster.this.id
  location = var.zone

  autoscaling {
    total_min_node_count = var.system_min_nodes
    total_max_node_count = var.system_max_nodes
    location_policy      = "BALANCED"
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type    = var.system_machine_type
    disk_size_gb    = 50
    disk_type       = "pd-balanced"
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels = {
      pool = "system"
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
}

resource "google_container_node_pool" "gpu" {
  for_each = local.gpu_pools

  name     = each.key
  cluster  = google_container_cluster.this.id
  location = var.zone

  autoscaling {
    total_min_node_count = 0
    total_max_node_count = each.value.max_nodes
    location_policy      = "ANY"
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type    = each.value.machine_type
    spot            = each.value.spot
    disk_size_gb    = 100
    disk_type       = "pd-balanced"
    image_type      = "COS_CONTAINERD"
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels = {
      pool = each.key
      gpu  = each.value.accelerator_type
    }

    guest_accelerator {
      type               = each.value.accelerator_type
      count              = each.value.accelerator_count
      gpu_partition_size = each.value.partition_size

      gpu_driver_installation_config {
        gpu_driver_version = each.value.driver_version
      }

      dynamic "gpu_sharing_config" {
        for_each = each.value.sharing == null ? [] : [each.value.sharing]
        content {
          gpu_sharing_strategy       = gpu_sharing_config.value.strategy
          max_shared_clients_per_gpu = gpu_sharing_config.value.clients
        }
      }
    }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
}
