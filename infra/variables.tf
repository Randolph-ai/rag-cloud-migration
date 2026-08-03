variable "qdrant_cloud_api_key" {
  description = "Qdrant Cloud Management API Key"
  type        = string
  sensitive   = true
}

variable "qdrant_cloud_account_id" {
  description = "Qdrant Cloud Account ID"
  type        = string
  sensitive   = true
}

variable "cluster_name" {
  description = "Name des Qdrant-Clusters"
  type        = string
  default     = "rag-migration-cluster"
}
