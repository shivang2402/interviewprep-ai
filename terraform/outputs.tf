output "backend_url" {
  description = "Backend Cloud Run service URL"
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_url" {
  description = "Frontend Cloud Run service URL"
  value       = google_cloud_run_v2_service.frontend.uri
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL instance connection name for Cloud Run"
  value       = google_sql_database_instance.main.connection_name
}

output "cloud_sql_ip" {
  description = "Cloud SQL public IP address"
  value       = google_sql_database_instance.main.public_ip_address
}

output "artifact_registry_url" {
  description = "Artifact Registry Docker repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "airflow_external_ip" {
  description = "Airflow VM external IP"
  value       = google_compute_instance.airflow.network_interface[0].access_config[0].nat_ip
}

output "mlflow_external_ip" {
  description = "MLflow VM external IP"
  value       = google_compute_instance.mlflow.network_interface[0].access_config[0].nat_ip
}

output "backend_service_account" {
  description = "Backend service account email"
  value       = google_service_account.backend.email
}
