terraform {
  required_version = ">= 1.7.0"
  required_providers {
    qdrant-cloud = {
      source  = "qdrant/qdrant-cloud"
      version = ">= 1.1.0"
    }
  }
}

provider "qdrant-cloud" {
  api_key    = var.qdrant_cloud_api_key
  account_id = var.qdrant_cloud_account_id
}

# Verfügbare Booking-Packages für AWS us-west-2 abfragen
data "qdrant-cloud_booking_packages" "all_packages" {
  cloud_provider = "aws"
  cloud_region   = "us-west-2"
}

locals {
  # Free-Tier-Paket: 1 GB RAM / entspricht in der Package-Liste
  # dem kleinsten verfügbaren Paket (0.5 CPU / 1Gi RAM ist üblich)
  desired_package = [
    for pkg in data.qdrant-cloud_booking_packages.all_packages.packages :
    pkg if pkg.resource_configuration[0].ram == "1Gi"
  ]
}

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

resource "qdrant-cloud_accounts_database_api_key_v2" "rag_key" {
  cluster_id = qdrant-cloud_accounts_cluster.rag_cluster.id
  name       = "rag-migration-key"
}

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
