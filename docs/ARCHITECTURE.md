# LectureMind — Architecture

This document describes the current implemented system architecture of LectureMind.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Component Architecture](#2-component-architecture)
3. [Async Task Pipeline (DAG)](#3-async-task-pipeline-dag)
4. [Data Model Hierarchy](#4-data-model-hierarchy)
5. [RAG System](#5-rag-system)
6. [Agentic RAG (LangGraph)](#6-agentic-rag-langgraph)
7. [Thumbnail & OCR Pipeline](#7-thumbnail--ocr-pipeline)
8. [Vector Store](#8-vector-store)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Deployment (Docker)](#10-deployment-docker)
11. [Configuration System](#11-configuration-system)
12. [Technical Decisions](#12-technical-decisions)

---

## 1. System Overview

LectureMind processes uploaded lecture videos through a multi-stage AI pipeline:

```
Upload → HLS Streaming
       → ASR Transcription
       → SSIM Slide Detection → Thumbnail Generation (dual-res) → Slide OCR
                                                                        │
                                                          Hybrid Chunking
                                                                │
                                              ┌─────────────────┼─────────────────┐
                                              │                 │                 │
                                   Fine-Grained KP    Coarse Summary      Generate Mindmap
                                              │                 │
                                         Embed Knowledge ───────┘
                                              │
                                         ChromaDB Vector Store
                                              │
                                      RAG Chatbot (3 modes)
```

---

## 2. Component Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + nginx)                       │
│                                                                       │
│   ┌────────────┐  ┌───────────┐  ┌──────────┐  ┌────────────────┐   │
│   │  Video     │  │ Knowledge │  │  Chat    │  │   Mindmap      │   │
│   │  Analysis  │  │ Explorer  │  │  Panel   │  │   Viewer       │   │
│   │  Page      │  │  Panel    │  │  (SSE)   │  │  (ReactFlow)   │   │
│   └─────┬──────┘  └─────┬─────┘  └────┬─────┘  └──────┬─────────┘  │
│         └───────────────┴──────────────┴───────────────┘            │
│                              │ REST + SSE                            │
│         API_PREFIX from window.__ENV__ (runtime-injectable)         │
└──────────────────────────────┼───────────────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────────────┐
│                    BACKEND (Django + Gunicorn)                        │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    REST API Layer (DRF)                         │  │
│  │  Video │ Section │ Knowledge │ Chat │ Mindmap │ Config │ Health │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │              Async Task Pipeline (DAG Executor)                 │  │
│  │  web process: Django/Gunicorn                                   │  │
│  │  worker process: manage.py process_async_task                   │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                       AI Service Layer                          │  │
│  │  LLM Client (OpenAI-compat) │ Embedding (sentence-transformers) │  │
│  │  RAGEngine (Fast RAG)       │ AgentGraph (LangGraph)            │  │
│  │  ASR Client (DashScope)     │ VectorStore (ChromaDB)            │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                       Storage Layer                             │  │
│  │  SQLite (DB_PATH) │ ChromaDB (CHROMA_PERSIST_DIR)              │  │
│  │  Media FS (MEDIA_ROOT) │ Tencent COS (audio for ASR)           │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 3. Async Task Pipeline (DAG)

The system uses a custom DAG executor (`manage.py process_async_task`):

- Tasks stored in `AsyncTaskItem` with a `previous` FK for dependency chaining
- Functions registered in `TASK_REGISTRY` in `api/tasks.py`
- Processor polls every 5 s; uses `SELECT FOR UPDATE SKIP LOCKED` for concurrency safety
- Task outputs are JSON-merged into dependent task inputs
- Progress tracked via `AsyncTaskItem.progress` (0–100)

**Full Task DAG:**

```
Upload Video
     │
     ├──→ task_extract_audio_and_transcript   (ASR via DashScope; audio → Tencent COS)
     ├──→ task_hls_streaming                  (FFmpeg → MEDIA_STREAMS_DIR)
     └──→ task_ssim_move_detection            (SSIM multithreaded slide change detection)
               │
               └──→ task_generate_thumbnails  (200px web + 1920px OCR → MEDIA_THUMBNAILS_DIR)
                         │
                         └──→ task_slides_ocr (VL model on image_high_res → SlideOCR)
                                   │
                                   └──→ task_hybrid_chunking
                                             │
                                             ├──→ task_fine_grained_knowledge
                                             ├──→ task_coarse_grained_summary
                                             ├──→ task_generate_mindmap
                                             └──→ task_embed_knowledge → ChromaDB
```

**Adding a new task type:**
1. Implement `def task_foo(input_data: Dict[str, Any]) -> Dict[str, Any]`
2. Register in `TASK_REGISTRY` in `api/tasks.py`
3. Chain by setting `previous` on the new `AsyncTaskItem`

---

## 4. Data Model Hierarchy

```
Episode (course/lecture series)
  └── Video
        ├── Thumbnail
        │     ├── image         (200px — web display, ImageField)
        │     └── image_high_res(1920px — OCR input, ImageField, nullable)
        ├── VideoTranscript (1:1, ASR metadata)
        │     └── TranscriptSentence (timestamped sentences)
        ├── AsyncTaskItem (pipeline task nodes)
        ├── SlideOCR (OCR text per thumbnail)
        ├── VideoSection (hybrid-chunker segments)
        │     └── KnowledgePoint (fine-grained LLM extraction per section)
        ├── KnowledgeSummary (1:1, coarse-grained video-level summary)
        ├── KnowledgeMindmap (1:1, hierarchical concept map JSON)
        ├── ChatSession
        │     └── ChatMessage (role, content, sources JSON, thinking_steps JSON)
        └── SystemConfig (key-value runtime configuration store)
```

---

## 5. RAG System

Three modes are available, each with fallback chains:

### LLM Direct (baseline)
- No retrieval; pure LLM response
- Used as hallucination baseline in evaluation

### Fast RAG
- Queries ChromaDB with the user question (top-k cosine similarity)
- Filters by `video_id` and optionally `content_type`
- Requires `MIN_DOCUMENTS_REQUIRED = 2` results above `MIN_RELEVANCE_THRESHOLD = 0.3`
- **Fallback**: drops to LLM Direct if retrieval quality is insufficient

### Agentic RAG
- LangGraph state machine; calls tools iteratively before synthesizing answer
- **Fallback chain**: Agentic → Fast RAG → LLM Direct

**Available agent tools** (`api/agent_tools.py`):

| Tool | Purpose |
|---|---|
| `search_knowledge` | Semantic search over knowledge points, sections, transcript sentences |
| `get_section_detail` | Fetch full content of a specific video section |
| `get_transcript_range` | Retrieve raw transcript between two timestamps |
| `search_slides` | Search slide OCR text (contact info, schedules, visual content) |

**Citation sanitization**: `agent_graph.py._sanitize_answer()` removes fabricated citation markers that do not correspond to actual retrieved sources.

---

## 6. Agentic RAG (LangGraph)

```
User Query
    │
    ▼
┌─────────────────────────────────────┐
│         LangGraph State Machine      │
│                                      │
│  entry → call_model                  │
│               │                      │
│          has tool calls?             │
│          ┌────┴────┐                 │
│         yes        no                │
│          │          │                │
│     run_tools    end (synthesize)    │
│          │                          │
│     call_model ◄───────────────────  │
└─────────────────────────────────────┘
    │
    ▼
_sanitize_answer()  ← strips hallucinated citations
    │
    ▼
Return answer + citations extracted from tool results
```

The agent system prompt (`AGENT_SYSTEM_PROMPT` in `agent_graph.py`) instructs the model on:
- Which tool to use for which query type
- Not to fabricate timestamps or citations
- Preferring `search_slides` for metadata questions (tutor info, schedules, contact details)

---

## 7. Thumbnail & OCR Pipeline

Dual-resolution thumbnail generation was introduced to improve OCR quality:

| Field | Width | Use |
|---|---|---|
| `Thumbnail.image` | 200 px | Web display (fast load) |
| `Thumbnail.image_high_res` | 1920 px | Slide OCR input |

**Generation flow** (`api/utils.py → generate_thumbnails_for_video()`):
1. Extract full-resolution frame from video via FFmpeg
2. Downscale to 200 px → save as `image`
3. Downscale to 1920 px → save as `image_high_res`

**OCR task** (`task_slides_ocr` in `api/tasks.py`):
- Uses `image_high_res` when available
- Falls back to `image` for thumbnails generated before this change
- Passes image to the VL model (`VL_MODEL` env var, default `qwen2.5-vl-72b-instruct`)
- Stores result in `SlideOCR.text`

---

## 8. Vector Store

`api/vector_store.py` wraps ChromaDB:

- **Persist directory**: `settings.CHROMA_PERSIST_DIR` → env `CHROMA_PERSIST_DIR` (default: `<MEDIA_ROOT>/chromadb`)
- **Embedding model**: `all-MiniLM-L6-v2` (sentence-transformers, runs locally)
- **Collection**: `lecture_knowledge` (single collection, filtered by `video_id` metadata)

**Content types stored:**

| `content_type` metadata | Source |
|---|---|
| `knowledge_point` | Fine-grained LLM extraction |
| `section` | Hybrid-chunker section summaries |
| `transcript` | Individual ASR transcript sentences |
| `slide_ocr` | Slide OCR text per thumbnail |
| `lecture_summary` | Coarse-grained video summary |

---

## 9. Frontend Architecture

- **Framework**: React 19 + TypeScript + Ant Design 6 + Tailwind CSS
- **Video player**: `@mux/mux-video-react` (HLS adaptive streaming)
- **Mindmap**: `@xyflow/react` (ReactFlow)
- **Routing**: React Router v7

**Runtime API URL injection:**

`frontend/public/env-config.js` is written by `docker-entrypoint.sh` at container start:
```js
window.__ENV__ = { API_PREFIX: "http://..." };
```
`src/config.ts` reads `window.__ENV__?.API_PREFIX` with a `http://127.0.0.1:8000` fallback for local `pnpm start`.

---

## 10. Deployment (Docker)

Three containers defined in `docker-compose.yml`:

| Service | Image | Role |
|---|---|---|
| `web` | `lecturemind-backend` | Django + Gunicorn API server |
| `worker` | `lecturemind-backend` (same image) | Async task processor (`SERVICE=worker`) |
| `frontend` | `lecturemind-frontend` | React SPA served by nginx on port 3000 |

Both `web` and `worker` mount the same named volume `lecturemind_data` at `/data`, which holds:
- `/data/db.sqlite3` — SQLite database
- `/data/media/` — uploaded videos, thumbnails, HLS streams, audio
- `/data/media/chromadb/` — ChromaDB vector store
- `/data/logs/` — rotating log files

**Backend image** (`server/Dockerfile`): 2-stage build (builder installs wheels; runtime is `python:3.11-slim` + FFmpeg). `docker-entrypoint.sh` runs `migrate` and `collectstatic` before starting Gunicorn or the worker.

**Frontend image** (`frontend/Dockerfile`): 2-stage build (node builds React; nginx serves static files). `docker-entrypoint.sh` writes `env-config.js` from `$API_PREFIX` before starting nginx.

**Quick start:**
```bash
cp .env.example .env   # fill in DASHSCOPE_API_KEY, COS_*, etc.
docker compose up --build
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
```

---

## 11. Configuration System

All runtime-variable settings are read from environment variables loaded from `.env`.

**Priority** (highest → lowest): shell env → `.env` file → Django default

**Key settings in `videoapp/settings.py`:**

| Django Setting | Env Variable | Default |
|---|---|---|
| `SECRET_KEY` | `SECRET_KEY` | insecure dev key |
| `DEBUG` | `DEBUG` | `True` |
| `ALLOWED_HOSTS` | `ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `DATABASES['NAME']` | `DB_PATH` | `<BASE_DIR>/db.sqlite3` |
| `MEDIA_ROOT` | `MEDIA_ROOT` | `<BASE_DIR>/media` |
| `MEDIA_URL` | `MEDIA_URL` | `/media/` |
| `MEDIA_AUDIO_DIR` | `MEDIA_AUDIO_DIR` | `<MEDIA_ROOT>/audio` |
| `MEDIA_STREAMS_DIR` | `MEDIA_STREAMS_DIR` | `<MEDIA_ROOT>/streams` |
| `MEDIA_THUMBNAILS_DIR` | `MEDIA_THUMBNAILS_DIR` | `<MEDIA_ROOT>/thumbnails` |
| `CHROMA_PERSIST_DIR` | `CHROMA_PERSIST_DIR` | `<MEDIA_ROOT>/chromadb` |
| `LOG_DIR` | `LOG_DIR` | `<BASE_DIR>/logs` |
| `CORS_ALLOWED_ORIGINS` | `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` |
| `BACKEND_PORT` | `BACKEND_PORT` | `8000` |

Sub-directory variables (`MEDIA_AUDIO_DIR`, etc.) accept either a relative name (resolved under `MEDIA_ROOT`) or an absolute path.

**LLM / API settings** (stored in `SystemConfig` model, readable via `ConfigManager`):

| Key | Env Variable | Description |
|---|---|---|
| `llm_model` | `LLM_MODEL` | Task pipeline LLM |
| `chat_model` | `CHAT_MODEL` | Chat / agent LLM |
| `vl_model` | `VL_MODEL` | Vision-language model for OCR |
| `llm_api_base` | `LLM_API_BASE` | OpenAI-compatible API base URL |
| `dashscope_api_key` | `DASHSCOPE_API_KEY` | DashScope API key |
| `cos_secret_id` | `COS_SECRECT_ID` | Tencent COS credentials |
| `cos_secret_key` | `COS_SECRECT_KEY` | Tencent COS credentials |
| `cos_region` | `COS_REGION` | Tencent COS region |
| `cos_bucket` | `COS_BUCKET` | Tencent COS bucket |

---

## 12. Technical Decisions

### Vector Database: ChromaDB
Chosen for zero-config embedded operation during development. Single collection `lecture_knowledge` filters by `video_id` metadata. Migration path to Qdrant/pgvector is straightforward as `VectorStore` is fully abstracted.

### Embedding Model: all-MiniLM-L6-v2
Runs locally via sentence-transformers; no additional API calls required. Must remain consistent across all upsert and query calls — changing the model requires re-embedding the entire collection.

### LLM Integration: OpenAI-compatible API
All LLM calls use the OpenAI client pointed at `LLM_API_BASE`. This makes the system model-agnostic; any OpenAI-compatible endpoint (DashScope, local vLLM, OpenAI itself) works without code changes.

### Task DAG: Single-dependency chain
`AsyncTaskItem.previous` is a single FK. Hybrid Chunking depends on the Thumbnail/OCR chain (which completes after SSIM) and reads the ASR transcript directly from the database (ASR typically finishes first). This avoids multi-dependency executor complexity.

### SQLite in Production
Acceptable for single-node deployments. The shared Docker volume ensures both `web` and `worker` access the same file. For multi-node or high-concurrency deployments, replace with PostgreSQL by setting `DB_PATH` to a PostgreSQL DSN and updating `DATABASES['ENGINE']`.

### Dual-Resolution Thumbnails
OCR quality was poor at 200 px. The solution generates both resolutions in one FFmpeg pass: full-res frame extracted first, then both sizes derived from it. The `image_high_res` field is nullable so existing thumbnails remain valid (OCR falls back to `image`).
