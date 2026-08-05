"""
/*******************************************************************************
 * MULTI-COLLECTION RAG BACKEND (FastAPI + Qdrant + OpenAI)
 *------------------------------------------------------------------------------
 * 📌 Beschreibung:
 *   Skalierbares Retrieval-Augmented Generation (RAG) System mit:
 *   - Isolierten Collections für domänenspezifische Dokumentensuche
 *   - Upload & Chunking (PDF/TXT) via LangChain
 *   - Collection-spezifischer QA mit OpenAI (GPT-4o-mini)
 *   - REST-API für Frontend/Externe Systeme
 *
 * 🛠️ Technischer Stack:
 *   - Backend: FastAPI (Python 3.10+)
 *   - Vektor-DB: Qdrant (1536-dim Embeddings, Cosine Distance)
 *   - LLM/Embeddings: OpenAI (text-embedding-3-small, gpt-4o-mini)
 *   - Dokumentenverarbeitung: LangChain (PyPDFLoader, RecursiveTextSplitter)
 *
 * 📂 API-Endpunkte:
 *   - /api/ask          → Collection-spezifische Fragen
 *   - /api/upload       → Dokumenten-Upload (PDF/TXT)
 *   - /api/collections  → Collection-Management (CRUD)
 *   - /api/health       → Systemstatus & Metriken
 *
 *------------------------------------------------------------------------------
 * 📝 Metadaten:
 *   Autor:       Randolph Bloomberg
 *   Organisation: Randolph Bloomberg 
 *   Version:     1.0.0
 *   Lizenz:      MIT (Open-Source)
 *   Erstellt:    17.09.2025
 *   Letzte Änd.: 04.08.2026
 *   Abhängigk.:  Siehe `requirements.txt`
 ******************************************************************************/
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_core.documents import Document
import os
import json
import shutil
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import re
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# LangChain Komponenten
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Qdrant Client
from qdrant_client import QdrantClient, models
from qdrant_client.http import models as rest_models

# ==================== KONFIGURATION ====================
load_dotenv()

# KORRIGIERT: Richtige Variablen aus .env lesen
QDRANT_SERVER_URL = os.getenv("QDRANT_SERVER_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEFAULT_COLLECTION = os.getenv("COLLECTION_NAME", "DSGVO")
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "./data/ETS")

# VALIDIERUNG DER KRITISCHEN VARIABLEN
if not OPENAI_API_KEY:
    raise ValueError("❌ OPENAI_API_KEY muss in der .env Datei gesetzt sein!")

if not QDRANT_SERVER_URL:
    raise ValueError("❌ QDRANT_SERVER_URL muss in der .env Datei gesetzt sein!")

print(f"✅ Konfiguration geladen: {DEFAULT_COLLECTION} auf {QDRANT_SERVER_URL}")

# Globale Services
qdrant_client = None
embeddings = None
llm = None

# ==================== MODELLE ====================
class ChatRequest(BaseModel):
    question: str
    collection_name: str = DEFAULT_COLLECTION
    search_type: str = "semantic"

class UploadRequest(BaseModel):
    collection_name: str = DEFAULT_COLLECTION

class CollectionInfo(BaseModel):
    name: str
    vectors_count: int
    documents_count: int  
    status: str

class SearchRequest(BaseModel):
    query: str
    collection_name: str = DEFAULT_COLLECTION
    search_type: str = "semantic"
    limit: int = 10

# ==================== LIFESPAN MANAGEMENT ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler für Startup/Shutdown"""
    global qdrant_client, embeddings, llm
    # Startup
    qdrant_client, embeddings, llm = initialize_services()
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    print("✅ Alle Services erfolgreich initialisiert")
    yield
    # Shutdown
    print("🛑 Services werden heruntergefahren")

# ==================== FASTAPI APP ====================
app = FastAPI(
    title="Multi-Collection Document QA", 
    version="2.0",
    lifespan=lifespan
)

# ==================== CORS KONFIGURATION ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8001",
        "https://rag-backend-mfmw3fed6q-ey.a.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== SERVICE-INITIALISIERUNG ====================
def initialize_services():
    """Initialisiert alle RAG-Komponenten"""
    try:
        client_config = {
            "url": QDRANT_SERVER_URL, 
            "timeout": 60.0, 
            "prefer_grpc": False
        }
        if QDRANT_API_KEY:
            client_config["api_key"] = QDRANT_API_KEY

        client = QdrantClient(**client_config)
        print(f"🔗 Verbunden mit Qdrant: {QDRANT_SERVER_URL}")

        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=OPENAI_API_KEY
        )
        print("✅ OpenAI Embeddings initialisiert")

        llm = ChatOpenAI(
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com/v1",
            openai_api_key=DEEPSEEK_API_KEY
        )
        print("✅ DeepSeek LLM initialisiert")

        return client, embeddings, llm

    except Exception as e:
        print(f"❌ Fehler bei Service-Initialisierung: {e}")
        raise HTTPException(status_code=500, detail=f"Service initialisierung fehlgeschlagen: {e}")

def get_vector_store(collection_name: str) -> QdrantVectorStore:
    """Erstellt einen Vector Store für eine spezifische Collection"""
    return QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        embedding=embeddings
    )

# ==================== KORRIGIERTE FUNKTIONEN ====================
def get_document_source(doc: Document) -> str:
    if not hasattr(doc, 'metadata') or not doc.metadata:
        return "Unbekannte Quelle"

    if 'source' in doc.metadata and doc.metadata['source']:
        source = doc.metadata['source']
        if isinstance(source, str) and source.strip():
            return source

    if 'document_name' in doc.metadata and doc.metadata['document_name']:
        return doc.metadata['document_name']

    if 'file_name' in doc.metadata and doc.metadata['file_name']:
        return doc.metadata['file_name']

    if 'original_path' in doc.metadata and doc.metadata['original_path']:
        return os.path.basename(doc.metadata['original_path'])

    return "Unbekannte Quelle"

def semantic_search(question: str, collection_name: str, limit: int = 5) -> List[Document]:
    """Verbesserte Suche mit Metadaten-Normalisierung"""
    try:
        vector_store = get_vector_store(collection_name)
        results = vector_store.similarity_search(question, k=limit)

        normalized_results = []
        for doc in results:
            if not hasattr(doc, 'metadata') or doc.metadata is None:
                doc.metadata = {}

            if doc == results[0]:
                print(f"🔍 Semantic Search - Metadaten-Struktur:")
                print(f"   - Keys: {list(doc.metadata.keys())}")

            normalized_results.append(doc)

        return normalized_results

    except Exception as e:
        print(f"❌ Semantic Search fehlgeschlagen: {e}")
        import traceback
        print(f"🔍 Detailed error: {traceback.format_exc()}")
        return []

def keyword_search(query: str, collection_name: str, limit: int = 5) -> List[Document]:
    """Keyword-Suche mit verbesserter Metadaten-Extraktion"""
    try:
        search_result = qdrant_client.search(
            collection_name=collection_name,
            query_filter=rest_models.Filter(
                must=[
                    rest_models.FieldCondition(
                        key="text",
                        match=rest_models.MatchText(text=query)
                    )
                ]
            ),
            limit=limit,
            with_payload=True,
        )

        documents = []
        for point in search_result:
            payload = point.payload or {}

            print(f"📦 Keyword-Suche Payload-Keys: {list(payload.keys())}")

            page_content = ""
            if 'text' in payload:
                page_content = payload['text']
            elif 'page_content' in payload:
                page_content = payload['page_content']

            metadata = {}
            if 'metadata' in payload and isinstance(payload['metadata'], dict):
                metadata = payload['metadata'].copy()
            else:
                for key, value in payload.items():
                    if key not in ['text', 'page_content']:
                        metadata[key] = value

            if 'source' not in metadata:
                for source_key in ['source', 'document_name', 'file_name']:
                    if source_key in payload:
                        metadata['source'] = payload[source_key]
                        break

            document = Document(
                page_content=page_content,
                metadata=metadata
            )
            documents.append(document)

        return documents
    except Exception as e:
        print(f"❌ Keyword-Suche fehlgeschlagen: {e}")
        return []

def hybrid_search(question: str, collection_name: str, limit: int = 5) -> List[Document]:
    """Kombiniert semantische und Keyword-Suche"""
    semantic_results = semantic_search(question, collection_name, limit * 2)
    keyword_results = keyword_search(question, collection_name, limit * 2)

    all_results = semantic_results + keyword_results
    unique_results = []
    seen_content = set()

    for doc in all_results:
        content_hash = hash(doc.page_content[:100])
        if content_hash not in seen_content:
            seen_content.add(content_hash)
            unique_results.append(doc)
        if len(unique_results) >= limit:
            break

    return unique_results

def get_collection_documents(collection_name: str, limit: int = 50) -> List[Document]:
    """Holt Dokumente mit korrekten Metadaten"""
    try:
        collections = qdrant_client.get_collections()
        if not any(col.name == collection_name for col in collections.collections):
            return []

        documents = []
        scroll_result = qdrant_client.scroll(
            collection_name=collection_name,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        for point in scroll_result[0]:
            payload = point.payload or {}

            page_content = payload.get("text", "") or payload.get("page_content", "")

            metadata = {}
            if 'metadata' in payload and isinstance(payload['metadata'], dict):
                metadata = payload['metadata'].copy()
            else:
                for key, value in payload.items():
                    if key not in ['text', 'page_content']:
                        metadata[key] = value

            document = Document(
                page_content=page_content,
                metadata=metadata
            )
            documents.append(document)

        return documents

    except Exception as e:
        print(f"❌ Fehler beim Abrufen der Dokumente: {e}")
        return []

def calculate_optimal_limit(question: str) -> int:
    """Berechnet optimales Limit basierend auf Fragelänge und Komplexität"""
    length = len(question)

    if length < 15:
        return 2
    elif length < 30:
        return 5
    elif length < 60:
        return 8
    else:
        return 15

def generate_collection_response(question: str, collection_name: str,
                               search_type: str = "semantic", limit: int = None) -> dict:
    if limit is None:
        limit = calculate_optimal_limit(question)
    print(f"🔍 Starte Suche in '{collection_name}' mit {search_type}")

    if search_type == "semantic":
        relevant_docs = semantic_search(question, collection_name, limit)
        search_method = "Semantische Suche"
    elif search_type == "keyword":
        relevant_docs = keyword_search(question, collection_name, limit)
        search_method = "Keyword-Suche"
    elif search_type == "hybrid":
        relevant_docs = hybrid_search(question, collection_name, limit)
        search_method = "Hybride Suche"
    else:
        relevant_docs = semantic_search(question, collection_name, limit)
        search_method = "Semantische Suche"

    print(f"📊 Gefundene Dokumente: {len(relevant_docs)}")

    document_mapping = {}
    context_sections = []

    for i, doc in enumerate(relevant_docs):
        source = get_document_source(doc)
        page = doc.metadata.get("page", "N/A")

        doc_ref = f"Dokument_{i+1}"
        document_mapping[doc_ref] = {
            "real_name": source,
            "page": page,
            "content": doc.page_content
        }

        context_sections.append(f"""
Dokument {i+1}:
- Name: {source}
- Seite: {page}
- Inhalt: {doc.page_content}
""")

    mapping_text = "\n".join([f"- {ref}: {info['real_name']} (Seite {info['page']})"
                            for ref, info in document_mapping.items()])

    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""Du bist ein präziser juristischer Assistent. 
         Beantworte die Frage ausführlich, aber präzise, basierend auf allen bereitgestellten Dokumenten.
**DOKUMENTEN-REFERENZEN:**
{mapping_text}
**ZITIERREGELN:**
1. Verwende IMMER den echten Dokumentnamen aus der "Name"-Spalte oben.
2. Format: "Laut [DOKUMENTNAME], Seite [X]: [Aussage]"
3. Verwende NIE generische Referenzen wie "Dokument 1", "Quelle 2", etc.
4. Sei präzise in der Quellenangabe.
**BEISPIEL:**
"Laut [DOKUMENTNAME].pdf, Seite 3: Das EU-ETS 2 regelt die Emissionen für Gebäude und Verkehr..."
**AKTUELLE DOKUMENTE:**


{chr(10).join(context_sections)}"""),
        ("human", f"FRAGE: {question}\n\nANTWORT (MIT EXPLIZITEN QUELLENANGABEN):")
    ])

    chain = prompt | llm
    response = chain.invoke({
        "question": question,
    })

    return {
        "answer": response.content,
        "sources": [get_document_source(doc) for doc in relevant_docs],
        "total_documents": count_unique_documents(collection_name),
        "relevant_documents": len(relevant_docs),
        "search_method": search_method
    }

def count_unique_documents(collection_name: str) -> int:
    """Zählt eindeutige PDF-Dateien"""
    try:
        test_docs = semantic_search("test", collection_name, limit=50)

        unique_pdfs = set()

        for doc in test_docs:
            source = get_document_source(doc)
            if source and source != "Unbekannte Quelle":
                clean_name = re.sub(r'.*[\\/]', '', source)
                if clean_name:
                    unique_pdfs.add(clean_name)
                    print(f"✅ PDF gefunden via get_document_source(): {clean_name}")

        count = len(unique_pdfs)
        print(f"📊 Collection '{collection_name}': {count} PDF-Dateien gefunden: {list(unique_pdfs)}")
        return count

    except Exception as e:
        print(f"❌ Fehler in count_unique_documents: {e}")
        return 0

# ==================== API-ENDPUNKTE ====================
@app.get("/api/simple-health")
async def simple_health_check():
    """Einfacher Health Check ohne Qdrant"""
    return {
        "status": "healthy", 
        "message": "FastAPI läuft",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

@app.get("/api/health")
async def health_check():
    """Health Check"""
    try:
        if qdrant_client and embeddings and llm:
            openai_status = "configured" if OPENAI_API_KEY else "missing"

            return {
                "status": "healthy",
                "services": {
                    "qdrant": "connected",
                    "openai": openai_status,
                    "backend": "running"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return {
                "status": "unhealthy", 
                "error": "Services not initialized",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@app.post("/api/ask")
async def ask_question(request: ChatRequest):
    try:
        print(f"🎯 ASK ENDPOINT CALLED: {request.question}")
        print(f"📝 Frage: {request.question} | Collection: {request.collection_name}")

        print(f"🔍 Prüfe Collection: {request.collection_name}")
        collections = qdrant_client.get_collections()
        collection_names = [col.name for col in collections.collections]
        print(f"📊 Verfügbare Collections: {collection_names}")

        if request.collection_name not in collection_names:
            print(f"❌ Collection nicht gefunden: {request.collection_name}")
            raise HTTPException(status_code=404, detail=f"Collection '{request.collection_name}' nicht gefunden")

        print("🔍 Validiere Collection-Metadaten...")
        test_docs = get_collection_documents(request.collection_name, limit=1)
        if test_docs:
            print(f"✅ Test-Dokument Metadaten: {test_docs[0].metadata}")

        result = generate_collection_response(
            question=request.question,
            collection_name=request.collection_name,
            search_type=request.search_type
        )

        print(f"✅ Quellen gefunden: {result['sources']}")
        print(f"✅ KI-Antwort generiert: {len(result['answer'])} Zeichen")

        return {
            "success": True,
            "question": request.question,
            "collection": request.collection_name,
            "answer": result["answer"],
            "metadata": {
                "sources": result["sources"],
                "total_documents": result["total_documents"],
                "relevant_documents": result["relevant_documents"],
                "search_method": result["search_method"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }

    except Exception as e:
        print(f"❌ Fehler in /api/ask: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")

@app.post("/api/search")
async def search_documents(request: SearchRequest):
    """Direkte Dokumentensuche (nur Retrieval, keine KI-Antwort)"""
    try:
        print(f"🔍 Suche in '{request.collection_name}': {request.query} (Type: {request.search_type})")

        collections = qdrant_client.get_collections()
        if not any(col.name == request.collection_name for col in collections.collections):
            raise HTTPException(status_code=404, detail=f"Collection '{request.collection_name}' nicht gefunden")

        if request.search_type == "semantic":
            results = semantic_search(request.query, request.collection_name, request.limit)
            search_method = "Semantische Suche"
        elif request.search_type == "keyword":
            results = keyword_search(request.query, request.collection_name, request.limit)
            search_method = "Keyword-Suche"
        elif request.search_type == "hybrid":
            results = hybrid_search(request.query, request.collection_name, request.limit)
            search_method = "Hybride Suche"
        else:
            results = semantic_search(request.query, request.collection_name, request.limit)
            search_method = "Semantische Suche"

        formatted_results = []
        for doc in results:
            formatted_results.append({
                "content": doc.page_content,
                "source": get_document_source(doc),
                "page": doc.metadata.get("page", None),
                "collection": doc.metadata.get("collection", request.collection_name)
            })

        return {
            "success": True,
            "query": request.query,
            "collection": request.collection_name,
            "search_method": search_method,
            "results": formatted_results,
            "total_results": len(formatted_results),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suchfehler: {str(e)}")

@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection_name: str = Query(DEFAULT_COLLECTION)
):
    """Dokument in spezifische Collection hochladen"""
    try:
        collections = qdrant_client.get_collections()
        if not any(col.name == collection_name for col in collections.collections):
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=1536,
                    distance=models.Distance.COSINE
                ),
            )
            print(f"✅ Neue Collection erstellt: {collection_name}")

        os.makedirs(DOCUMENTS_DIR, exist_ok=True)
        file_path = os.path.join(DOCUMENTS_DIR, file.filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if file.filename.endswith(".pdf"):
            loader = PyPDFLoader(file_path)
        elif file.filename.endswith(".txt"):
            loader = TextLoader(file_path, encoding='utf-8')
        else:
            os.remove(file_path)
            return {"error": "Nur PDF und TXT Dateien unterstützt"}

        documents = loader.load()
        for doc in documents:
            doc.metadata.update({
                "source": file.filename,
                "file_name": file.filename,
                "pdf_name": file.filename.replace('.pdf', '').replace('.txt', ''),
                "collection": collection_name,
                "upload_time": datetime.now(timezone.utc).isoformat()
            })

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = splitter.split_documents(documents)

        QdrantVectorStore.from_documents(
            chunks,
            embeddings,
            url=QDRANT_SERVER_URL,
            api_key=QDRANT_API_KEY if QDRANT_API_KEY else None,
            collection_name=collection_name,
            force_recreate=False
        )

        os.remove(file_path)

        return {
            "success": True,
            "filename": file.filename,
            "chunks_created": len(chunks),
            "collection": collection_name,
            "message": f"Dokument in Collection '{collection_name}' gespeichert"
        }

    except Exception as e:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        return {"error": str(e)}

@app.get("/api/collections")
async def get_collections():
    """Collections API OHNE Fallbacks"""
    try:
        print("🎯 Collections API aufgerufen")

        # ✅ KORRIGIERT: Verwende globale QDRANT_SERVER_URL statt localhost
        client = QdrantClient(url=QDRANT_SERVER_URL, api_key=QDRANT_API_KEY)
        collections_response = client.get_collections()

        print(f"📊 Verfügbare Qdrant Collections: {[col.name for col in collections_response.collections]}")

        collections = []
        for collection in collections_response.collections:
            try:
                collection_info = client.get_collection(collection_name=collection.name)

                unique_pdfs = set()
                scroll_result = client.scroll(
                    collection_name=collection.name,
                    limit=1000,
                    with_payload=True,
                    with_vectors=False
                )

                for point in scroll_result[0]:
                    payload = point.payload or {}
                    source = (
                        payload.get('source') or 
                        payload.get('file_name') or 
                        payload.get('document_name') or
                        payload.get('pdf_name')
                    )

                    if source:
                        clean_source = re.sub(r'.*[\\/]', '', source)
                        if clean_source and '.pdf' in clean_source.lower():
                            unique_pdfs.add(clean_source)

                pdf_count = len(unique_pdfs)
                print(f"✅ Collection {collection.name}: {pdf_count} PDFs gefunden - {list(unique_pdfs)}")

                collections.append({
                    "name": collection.name,
                    "vectors_count": pdf_count,
                    "points_count": collection_info.points_count
                })

            except Exception as e:
                print(f"❌ Fehler bei Collection {collection.name}: {e}")
                # ✅ KEIN FALLBACK - Collection wird übersprungen
                continue

        print(f"🎯 Finale Collections: {collections}")
        return {"collections": collections}

    except Exception as e:
        print(f"💥 Kritischer Fehler in /api/collections: {e}")
        # ✅ KEIN FALLBACK - nur Fehler zurückgeben
        return {"collections": [], "error": str(e)}

@app.get("/api/debug-all-metadata")
async def debug_all_metadata(collection_name: str = "DSGVO"):
    """Zeigt ALLE Metadaten-Felder für die ersten 5 Punkte"""
    try:
        points, _ = qdrant_client.scroll(
            collection_name=collection_name,
            limit=5,
            with_payload=True
        )

        debug_data = []
        for i, point in enumerate(points):
            payload = point.payload or {}
            debug_data.append({
                "point": i + 1,
                "all_payload_keys": list(payload.keys()),
                "complete_payload": payload,
            })

        return {"debug_data": debug_data}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/debug-sources")
async def debug_sources(collection_name: str = "DSGVO"):
    """Debug-Endpoint für Quellen-Extraktion"""
    try:
        test_docs = semantic_search("test", collection_name, limit=3)

        debug_info = []
        for i, doc in enumerate(test_docs):
            source = get_document_source(doc)
            debug_info.append({
                "document": i + 1,
                "extracted_source": source,
                "metadata_keys": list(doc.metadata.keys()) if doc.metadata else [],
                "document_name": doc.metadata.get('document_name', 'N/A'),
                "source_field": doc.metadata.get('source', 'N/A')
            })

        return {"debug_info": debug_info}
    except Exception as e:
        return {"error": str(e)}

# ==================== SERVER START ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)