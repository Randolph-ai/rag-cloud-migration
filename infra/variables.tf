# ============================================================
# TERRAFORM VARIABLEN - QDRANT & GCP INFRASTRUKTUR
# ============================================================
#
# METADATEN:
#   Autor:           Randolph Bluming
#   Erstellt am:     2026-08-04
#   Letzte Änderung: 2026-08-04
#   Version:         1.0.0
#
# ZWECK:
#   Zentrale Variablendefinition für Qdrant Cloud, GCP und externe APIs.
#   Sensible Werte (API-Keys) sind als "sensitive" markiert.
#
# VERWENDUNG:
#   - Werte können in terraform.tfvars oder als Umgebungsvariablen
#     (TF_VAR_*) übergeben werden.
#   - In der GitHub Actions Pipeline werden sie als Secrets injiziert.
# ============================================================

# ============================================================
# QDRANT CLOUD - MANAGEMENT
# ============================================================

# API-Key für die Qdrant Cloud Management API
# → Wird für alle administrativen Operationen benötigt
variable "qdrant_cloud_api_key" {
  description = "Qdrant Cloud Management API Key"
  type        = string
  sensitive   = true
}

# Account-ID des Qdrant Cloud Accounts
# → Identifiziert den Account für API-Aufrufe
variable "qdrant_cloud_account_id" {
  description = "Qdrant Cloud Account ID"
  type        = string
  sensitive   = true
}

# Name des Qdrant-Clusters
# → Wird im Qdrant Cloud Dashboard angezeigt
variable "cluster_name" {
  description = "Name des Qdrant-Clusters"
  type        = string
  default     = "rag-migration-cluster"
}

# ============================================================
# GOOGLE CLOUD PLATFORM
# ============================================================

# GCP Projekt-ID
# → Identifiziert das Projekt für alle GCP-Ressourcen
variable "gcp_project_id" {
  description = "Google Cloud Projekt-ID"
  type        = string
  default     = "rag-system-ai-504412"
}

# GCP Region für Cloud Run und andere Services
# → Alle Ressourcen werden in dieser Region deployt
variable "gcp_region" {
  description = "Google Cloud Region für Cloud Run"
  type        = string
  default     = "europe-west3"
}

# ============================================================
# EXTERNE APIS (nicht Qdrant)
# ============================================================

# OpenAI API Key für Embeddings
# → Wird vom Backend für die Vektorisierung verwendet
variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true
}

# Qdrant Collection Name
# → Definiert die Collection für die Vektorsuche
variable "collection_name" {
  description = "Qdrant Collection Name"
  type        = string
  default     = "ETS-2"
}

# DeepSeek API Key für Antwortgenerierung
# → Alternative zu OpenAI für bestimmte Use-Cases
variable "deepseek_api_key" {
  description = "DeepSeek API Key für die Antwortgenerierung"
  type        = string
  sensitive   = true
}
