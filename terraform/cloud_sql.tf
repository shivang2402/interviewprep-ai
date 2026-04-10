# ─────────────────────────────────────────────
# Cloud SQL — PostgreSQL with pgvector
# ─────────────────────────────────────────────

resource "google_sql_database_instance" "main" {
  name             = var.db_instance_name
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier              = "db-custom-2-7680" # 2 vCPU, 7.5GB RAM
    availability_type = "REGIONAL"         # HA with automatic failover
    disk_size         = 20                 # GB
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00" # 3 AM UTC
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 7
      }
    }

    ip_configuration {
      ipv4_enabled = true # Set to false and use private_network for production
      # For production: uncomment below and set ipv4_enabled = false
      # private_network = google_compute_network.vpc.id

      authorized_networks {
        name  = "allow-all-temporary"
        value = "0.0.0.0/0"
      }
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 4 # 4 AM UTC
      update_track = "stable"
    }
  }

  deletion_protection = true

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "main" {
  name     = var.db_name
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "postgres" {
  name     = "postgres"
  instance = google_sql_database_instance.main.name
  password = var.db_password
}
