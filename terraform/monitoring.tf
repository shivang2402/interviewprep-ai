# ─────────────────────────────────────────────
# Cloud Monitoring — Uptime checks & alerts
# ─────────────────────────────────────────────

resource "google_monitoring_uptime_check_config" "backend_health" {
  display_name = "InterviewPrep Backend Health"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path         = "/api/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.backend.uri, "https://")
    }
  }
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "InterviewPrep Team Email"
  type         = "email"

  labels = {
    email_address = "kansara.dh@northeastern.edu"
  }
}

resource "google_monitoring_alert_policy" "backend_error_rate" {
  display_name = "Backend Error Rate > 5%"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run 5xx error rate"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"interviewprep-backend\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "backend_latency" {
  display_name = "Backend p95 Latency > 5s"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run request latency"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"interviewprep-backend\" AND metric.type = \"run.googleapis.com/request_latencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5000 # 5 seconds in ms
      duration        = "300s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }
}
