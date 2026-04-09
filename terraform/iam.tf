# ─────────────────────────────────────────────
# Service Accounts & IAM Bindings
# ─────────────────────────────────────────────

# Backend Cloud Run service account
resource "google_service_account" "backend" {
  account_id   = "cloudrun-backend-sa"
  display_name = "Cloud Run Backend Service Account"
}

resource "google_project_iam_member" "backend_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_secret" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# Frontend Cloud Run service account (minimal permissions)
resource "google_service_account" "frontend" {
  account_id   = "cloudrun-frontend-sa"
  display_name = "Cloud Run Frontend Service Account"
}

# Airflow / pipeline service account
resource "google_service_account" "airflow" {
  account_id   = "airflow-pipeline-sa"
  display_name = "Airflow Pipeline Service Account"
}

resource "google_project_iam_member" "airflow_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.airflow.email}"
}

resource "google_project_iam_member" "airflow_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.airflow.email}"
}

resource "google_project_iam_member" "airflow_secret" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.airflow.email}"
}
