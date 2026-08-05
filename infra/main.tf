# ============================================================
# TERRAFORM - QDRANT CLOUD & GCP INFRASTRUKTUR
# ============================================================
# Autor:    Randolph Bluming
# Erstellt: 2026-08-04
# Version:  1.0.0
# Zweck:    Qdrant Cloud Cluster + GCP Cloud Run Backend
# ============================================================

# ============================================================
# TERRAFORM KONFIGURATION
# ============================================================
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    qdrant-cloud = {
      source  = "qdrant/qdrant-cloud"
      version = ">= 1.1.0"
    }
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

# ============================================================
# PROVIDER
# ============================================================
provider "qdrant-cloud" {
  api_key    = var.qdrant_cloud_api_key
  account_id = var.qdrant_cloud_account_id
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# ============================================================
# DATA SOURCE: VERFÜGBARE PACKAGES
# ============================================================
# Qdrant Cloud Packages für AWS us-west-2 abfragen
data "qdrant-cloud_booking_packages" "all_packages" {
  cloud_provider = "aws"
  cloud_region   = "us-west-2"
}

# ============================================================
# LOCALS: FREE-TIER PACKAGE FILTERN
# ============================================================
# Filtert das Package mit 1Gi RAM (Free-Tier)
locals {
  desired_package = [
    for pkg in data.qdrant-cloud_booking_packages.all_packages.packages :
    pkg if pkg.resource_configuration[0].ram == "1Gi"
  ]
}

# ============================================================
# RESOURCE: QDRANT CLUSTER
# ============================================================
# Erstellt den Qdrant Cloud Cluster (1 Node, Free-Tier)
resource "qdrant-cloud_accounts_cluster" "rag_cluster" {
  name           = var.cluster_name
  cloud_provider = data.qdrant-cloud_booking_packages.all_packages.cloud_provider
  cloud_region   = data.qdrant-cloud_booking_packages.all_packages.cloud_region

  configuration {
    number_of_nodes = 1
    node_configuration {
      package_id = local.desired_package[0].id
    }
  }
}

# ============================================================
# RESOURCE: GCP CLOUD RUN SERVICE
# ============================================================
# Deployt den RAG-Backend-Container auf Cloud Run
resource "google_cloud_run_v2_service" "rag_backend" {
  name     = "rag-backend"
  location = var.gcp_region
  deletion_protection = false

  template {
    containers {
      image = "europe-west3-docker.pkg.dev/${var.gcp_project_id}/rag-migration-repo/rag-backend:v5"

      ports {
        container_port = 8080
      }

      # ---- Umgebungsvariablen für den Container ----
      env {
        name  = "OPENAI_API_KEY"
        value = var.openai_api_key
      }
      env {
        name  = "QDRANT_SERVER_URL"
        value = qdrant-cloud_accounts_cluster.rag_cluster.url
      }
      env {
        name  = "DEEPSEEK_API_KEY"
        value = var.deepseek_api_key
      }
      env {
        name  = "QDRANT_API_KEY"
        value = qdrant-cloud_accounts_database_api_key_v2.rag_key.key
      }
      env {
        name  = "COLLECTION_NAME"
        value = var.collection_name
      }
    }
  }
}

# ============================================================
# RESOURCE: CLOUD RUN PUBLIC ACCESS
# ============================================================
# Ermöglicht öffentlichen Zugriff auf den Cloud Run Service
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.rag_backend.location
  name     = google_cloud_run_v2_service.rag_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ============================================================
# RESOURCE: QDRANT API KEY
# ============================================================
# Erstellt einen API-Key für den Qdrant-Datenbankzugriff
resource "qdrant-cloud_accounts_database_api_key_v2" "rag_key" {
  cluster_id = qdrant-cloud_accounts_cluster.rag_cluster.id
  name       = "rag-migration-key"
}

# ============================================================
# OUTPUTS
# ============================================================
output "cluster_url" {
  value = qdrant-cloud_accounts_cluster.rag_cluster.url
}

output "cluster_id" {
  value = qdrant-cloud_accounts_cluster.rag_cluster.id
}

output "cluster_api_key" {
  value     = qdrant-cloud_accounts_database_api_key_v2.rag_key.key
  sensitive = true
}