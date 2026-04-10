variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "professorbot-dovbsg"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "db_name" {
  description = "Cloud SQL database name"
  type        = string
  default     = "interviewprep-ai-database"
}

variable "db_instance_name" {
  description = "Cloud SQL instance name"
  type        = string
  default     = "interviewprep-ai-db"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key for RAG generation"
  type        = string
  sensitive   = true
}

variable "backend_image" {
  description = "Backend Docker image URL"
  type        = string
  default     = "us-central1-docker.pkg.dev/professorbot-dovbsg/interviewprep-ai/backend:latest"
}

variable "frontend_image" {
  description = "Frontend Docker image URL"
  type        = string
  default     = "us-central1-docker.pkg.dev/professorbot-dovbsg/interviewprep-ai/frontend:latest"
}

variable "backend_min_instances" {
  description = "Minimum backend Cloud Run instances (1 avoids cold starts)"
  type        = number
  default     = 1
}

variable "frontend_min_instances" {
  description = "Minimum frontend Cloud Run instances (0 allows scale to zero)"
  type        = number
  default     = 0
}
