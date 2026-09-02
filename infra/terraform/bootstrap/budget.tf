resource "google_monitoring_notification_channel" "budget_email" {
  count = var.create_budget && var.alert_email != "" ? 1 : 0

  project      = google_project.this.project_id
  display_name = "Budget alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }

  depends_on = [time_sleep.api_propagation]
}

resource "google_billing_budget" "monthly" {
  count    = var.create_budget ? 1 : 0
  provider = google.budget

  billing_account = var.billing_account
  display_name    = "${var.project_id}-monthly"

  budget_filter {
    projects = ["projects/${google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  dynamic "all_updates_rule" {
    for_each = var.alert_email != "" ? [1] : []
    content {
      monitoring_notification_channels = [google_monitoring_notification_channel.budget_email[0].id]
      disable_default_iam_recipients   = false
    }
  }

  depends_on = [time_sleep.api_propagation]
}
