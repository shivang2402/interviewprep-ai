# ─────────────────────────────────────────────
# Cloud Run — Backend (FastAPI + RAG)
# ─────────────────────────────────────────────
resource "google_cloud_run_v2_service" "backend" {
  name     = "interviewprep-backend"
  location = var.region

  template {
    scaling {
      min_instance_count = var.backend_min_instances
      max_instance_count = 10
    }

    service_account = google_service_account.backend.email

    containers {
      image = var.backend_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "DB_CONNECTION_MODE"
        value = "socket"
      }
      env {
        name  = "CLOUD_SQL_INSTANCE_CONNECTION_NAME"
        value = "${var.project_id}:${var.region}:${var.db_instance_name}"
      }
      env {
        name  = "DB_NAME"
        value = var.db_name
      }
      env {
        name  = "DB_USER"
        value = "postgres"
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "USE_SECRET_MANAGER"
        value = "false"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "EMBEDDING_MODEL"
        value = "all-MiniLM-L6-v2"
      }
      env {
        name  = "ALLOWED_ORIGINS"
        value = google_cloud_run_v2_service.frontend.uri
      }
      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai_api_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/api/health"
          port = 8000
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 12 # Allow up to 60s for model loading
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = ["${var.project_id}:${var.region}:${var.db_instance_name}"]
      }
    }

    timeout = "300s"
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.db_password,
    google_secret_manager_secret_version.openai_api_key,
  ]
}

# Allow unauthenticated access to backend
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ─────────────────────────────────────────────
# Cloud Run — Frontend (Next.js)
# ─────────────────────────────────────────────
resource "google_cloud_run_v2_service" "frontend" {
  name     = "interviewprep-frontend"
  location = var.region

  template {
    scaling {
      min_instance_count = var.frontend_min_instances
      max_instance_count = 5
    }

    service_account = google_service_account.frontend.email

    containers {
      image = var.frontend_image

      ports {
        container_port = 3000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "NEXT_PUBLIC_API_BASE_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Allow unauthenticated access to frontend
resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
