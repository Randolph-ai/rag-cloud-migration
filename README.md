---
title: RAG Migration Demo
emoji: 🔍
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# RAG-System: FastAPI + Qdrant Cloud + Hugging Face Spaces

Kostengünstige (0 €/Monat) Cloud-Migration eines RAG-Systems, provisioniert via Terraform.

**Architektur:**
- Backend: FastAPI (Python 3.11)
- Vektordatenbank: Qdrant Cloud (Free Tier), provisioniert via Terraform
- LLM/Embeddings: OpenAI (gpt-4o-mini, text-embedding-3-small)
- Deployment: Hugging Face Spaces (Docker SDK)
