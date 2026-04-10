# ─────────────────────────────────────────────
# Compute Engine — Airflow VM
# ─────────────────────────────────────────────
resource "google_compute_instance" "airflow" {
  name         = "airflow-server"
  machine_type = "e2-standard-2" # 2 vCPU, 8GB RAM
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 50 # GB
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"

    access_config {
      # Ephemeral external IP for SSH access
    }
  }

  service_account {
    email  = google_service_account.airflow.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = <<-SCRIPT
    #!/bin/bash
    set -e

    # Install Python 3.11
    apt-get update
    apt-get install -y python3.11 python3.11-venv python3-pip git

    # Create airflow user
    useradd -m -s /bin/bash airflow || true

    # Set up Airflow
    su - airflow -c '
      python3.11 -m venv ~/airflow-venv
      source ~/airflow-venv/bin/activate
      pip install apache-airflow==2.9.3 psycopg2-binary
      airflow db init
    '

    echo "Airflow setup complete. Upload DAGs to /home/airflow/airflow/dags/"
  SCRIPT

  tags = ["airflow-server", "http-server"]

  depends_on = [google_project_service.apis]
}

# ─────────────────────────────────────────────
# Compute Engine — MLflow VM
# ─────────────────────────────────────────────
resource "google_compute_instance" "mlflow" {
  name         = "mlflow-server"
  machine_type = "e2-standard-2"
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 50
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"

    access_config {}
  }

  service_account {
    email  = google_service_account.airflow.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = <<-SCRIPT
    #!/bin/bash
    set -e

    apt-get update
    apt-get install -y python3.11 python3.11-venv python3-pip

    useradd -m -s /bin/bash mlflow || true

    su - mlflow -c '
      python3.11 -m venv ~/mlflow-venv
      source ~/mlflow-venv/bin/activate
      pip install mlflow psycopg2-binary google-cloud-storage
    '

    echo "MLflow setup complete. Start with: mlflow server --host 0.0.0.0 --port 5000"
  SCRIPT

  tags = ["mlflow-server"]

  depends_on = [google_project_service.apis]
}

# ─────────────────────────────────────────────
# Firewall rules
# ─────────────────────────────────────────────
resource "google_compute_firewall" "allow_airflow" {
  name    = "allow-airflow-webserver"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  source_ranges = ["0.0.0.0/0"] # Restrict to your IP in production
  target_tags   = ["airflow-server"]
}

resource "google_compute_firewall" "allow_mlflow" {
  name    = "allow-mlflow"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["5000"]
  }

  source_ranges = ["0.0.0.0/0"] # Restrict to Airflow VM + GitHub Actions IPs in production
  target_tags   = ["mlflow-server"]
}
