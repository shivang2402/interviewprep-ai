# ─────────────────────────────────────────────
# Artifact Registry — Docker image repository
# ─────────────────────────────────────────────
resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "interviewprep-ai"
  format        = "DOCKER"
  description   = "InterviewPrep AI container images"

  depends_on = [google_project_service.apis]
}
