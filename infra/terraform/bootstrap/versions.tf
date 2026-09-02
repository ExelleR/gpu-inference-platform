terraform {
  required_version = ">= 1.5.7"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.1"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.13"
    }
  }
}
