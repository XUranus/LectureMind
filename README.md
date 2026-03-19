# PolyU Video Agent

An AI-powered lecture video analysis and summarization platform. Upload lecture videos, and the system automatically segments them, transcribes speech, detects slide transitions, generates knowledge summaries, and provides an intelligent chatbot for Q&A over lecture content.

![Transcript View](screenshot/transcript.png)

---

## Table of Contents

- [Project Background](#project-background)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Video-RAG Pipeline](#video-rag-pipeline)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Data Models](#data-models)
- [Async Task Pipeline](#async-task-pipeline)
- [Roadmap](#roadmap)

---

## Project Background

The **PolyU Video Agent** is an advanced AI system designed to process lecture videos through a multi-stage pipeline: segmenting lectures into meaningful sections, transcribing audio to text, detecting slide transitions, summarizing concepts at multiple granularities, and enabling knowledge-point retrieval through a RAG-based chatbot.

The system transforms raw lecture video input into structured, searchable, and summarized knowledge, making it easy for students and educators to navigate, review, and query lecture content.

---

## Features

### Implemented

| Feature | Description |
|---------|-------------|
| **Video Upload & Management** | Drag-and-drop upload with progress tracking, CRUD operations, course/episode grouping |
| **HLS Adaptive Streaming** | Multi-resolution transcoding (1080p/720p/480p/360p) with master playlist for adaptive playback |
| **ASR Transcription** | Automatic speech recognition via Alibaba DashScope Qwen3-ASR with sentence-level timestamps, language detection, emotion tagging |
| **SSIM Slide Detection** | Multithreaded structural similarity analysis to detect slide transitions with configurable thresholds |
| **Thumbnail Generation** | Automatic thumbnail extraction at detected slide change points |
| **Async Task Pipeline** | DAG-based task execution engine with dependency chaining, concurrent processing, and error isolation |
| **Task Monitoring Dashboard** | Real-time task status tracking with per-video task groups |
| **Interactive Transcript Viewer** | Clickable sentence-level transcript with video seek synchronization |
| **Course Organization** | Group videos into courses/episodes with nested management |

### Planned

| Feature | Description |
|---------|-------------|
| **Fine-Grained Knowledge Summarization** | Per-slide/segment analysis combining slide screenshot + transcript for knowledge point extraction |
| **Coarse-Grained Knowledge Summarization** | Cross-segment knowledge combination and thematic chapter generation |
| **Video-RAG System** | Retrieval-augmented generation over lecture content using vector embeddings and semantic search |
| **Lecture Chatbot** | LLM-powered conversational Q&A grounded in lecture transcripts, slides, and knowledge summaries |
| **Knowledge Mindmap Generation** | Automatic generation of hierarchical concept maps from lecture content |
| **Hybrid Chunking** | Combined slide detection + silence gaps + semantic shift analysis for intelligent lecture segmentation |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Frontend (React + TypeScript)                   │
│  ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌────────┐ ┌───────────┐  │
│  │  Upload   │ │ Video Player │ │Transcript │ │Chatbot │ │  Mindmap  │  │
│  │Dashboard │ │  (HLS/Mux)   │ │  Viewer   │ │  Panel │ │  Viewer   │  │
│  └──────────┘ └──────────────┘ └───────────┘ └────────┘ └───────────┘  │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │ REST API
┌──────────────────────────┴──────────────────────────────────────────────┐
│                      Backend (Django + DRF)                              │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                    Synchronous API Layer                           │   │
│  │  Video CRUD │ Episode CRUD │ Transcript API │ Task API │ Chat API │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │              Async Task Processor (manage.py process_async_task)   │   │
│  │                                                                    │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                           │   │
│  │  │  ASR    │  │  HLS    │  │  SSIM   │  (Parallel, no deps)      │   │
│  │  │Transcr. │  │Encoding │  │Detection│                           │   │
│  │  └─────────┘  └─────────┘  └────┬────┘                           │   │
│  │                                  │                                 │   │
│  │                             ┌────┴────┐                           │   │
│  │                             │Thumbnail│                           │   │
│  │                             │  Gen.   │                           │   │
│  │                             └────┬────┘                           │   │
│  │                                  │                                 │   │
│  │                          ┌───────┴───────┐                        │   │
│  │                          │  AI Summary   │                        │   │
│  │                          │  (Knowledge)  │                        │   │
│  │                          └───────────────┘                        │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                      AI / ML Services                              │   │
│  │  DashScope ASR │ LLM (Qwen) │ Embeddings │ Vector DB │ LangGraph │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                      Storage                                       │   │
│  │  SQLite (metadata) │ Tencent COS (audio) │ Local FS (media/HLS)   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Video-RAG Pipeline

The core AI functionality is powered by a **Video-RAG (Retrieval-Augmented Generation)** pipeline that processes videos through hierarchical granularities:

### Stage 1: Video Preprocessing
- **SSIM Slide Detection**: Frame-by-frame structural similarity comparison to identify slide transition timestamps
- **Audio Extraction**: Separate audio track using FFmpeg/pydub, convert to 16kHz mono WAV
- **HLS Transcoding**: Generate multi-resolution adaptive streaming segments

### Stage 2: Content Extraction
- **ASR Transcription**: Qwen3-ASR produces sentence-level transcripts with timestamps, language codes, and emotion tags
- **Slide Screenshot Capture**: Extract representative frames at detected transition points
- **Hybrid Chunking**: Combine slide transitions + silence gaps + semantic similarity (sentence-transformers) to produce intelligent content segments

### Stage 3: Fine-Grained Knowledge Store (Planned)
For each video segment (slide + corresponding transcript):
- Extract knowledge points using multimodal LLM (slide image + transcript text)
- Generate per-segment summaries, key concepts, and terminology
- Create dense vector embeddings for semantic retrieval
- Store in vector database with metadata (timestamps, segment boundaries)

### Stage 4: Coarse-Grained Knowledge Store (Planned)
Aggregate fine-grained knowledge across segments:
- Identify thematic chapters by clustering related segments
- Generate lecture-level summaries, outlines, and concept hierarchies
- Build cross-reference links between related knowledge points
- Produce structured mindmaps from the knowledge hierarchy

### Stage 5: RAG Query Engine (Planned)
- **Retrieval**: Semantic search over fine-grained and coarse-grained knowledge stores
- **Augmentation**: Construct context windows from retrieved segments (transcript + slide + summary)
- **Generation**: LLM generates grounded answers with source citations and timestamp references
- **Agent Orchestration**: LangGraph manages multi-step reasoning, tool selection, and context assembly

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, TypeScript, Tailwind CSS, Ant Design 6 |
| **Video Player** | @mux/mux-video-react (HLS adaptive streaming) |
| **Backend** | Python 3.10, Django 5.2, Django REST Framework |
| **ASR** | Alibaba DashScope Qwen3-ASR (async file transcription) |
| **Computer Vision** | OpenCV, scikit-image (SSIM), Pillow |
| **Video Processing** | FFmpeg (HLS encoding, audio extraction), pydub |
| **NLP/Embeddings** | sentence-transformers (all-MiniLM-L6-v2) |
| **LLM** | Qwen2.5 series (planned: 0.5B-7B local, qwen-turbo remote) |
| **Cloud Storage** | Tencent COS (audio file hosting for ASR) |
| **Database** | SQLite (development), planned migration to PostgreSQL |
| **Agent Framework** | LangGraph (planned) |
| **Vector Database** | TBD (ChromaDB / Milvus / Qdrant) |

---

## Project Structure

```
PolyU-Video-Agent/
├── README.md
├── LICENSE                          # Apache 2.0
├── .env                             # Environment variables (COS, DashScope keys)
├── .env.example                     # Template for environment setup
│
├── server/
│   ├── requirements.txt             # Python dependencies
│   ├── environment.yml              # Conda environment specification
│   ├── demo/                        # Standalone demo scripts
│   │   ├── demo_dashscope_asr.py
│   │   └── demo_lecture_video_hybrid_chunker.py
│   └── app/
│       ├── manage.py                # Django management entry point
│       ├── videoapp/                # Django project configuration
│       │   ├── settings.py          # Database, CORS, logging, media config
│       │   ├── urls.py              # Root URL routing
│       │   ├── wsgi.py
│       │   └── asgi.py
│       ├── api/                     # Main Django application
│       │   ├── models.py            # Episode, Video, Thumbnail, Transcript, AsyncTask
│       │   ├── serializers.py       # DRF serializers
│       │   ├── views.py             # API views (CRUD, upload, task trigger)
│       │   ├── urls.py              # API URL patterns
│       │   ├── tasks.py             # Async task implementations + registry
│       │   ├── utils.py             # FFmpeg/HLS/thumbnail utilities
│       │   ├── dashscope_asr.py     # DashScope Qwen3-ASR client
│       │   ├── lecture_video_slides_chunker.py   # SSIM slide detection
│       │   ├── lecture_video_hybrid_chunker.py    # Hybrid semantic chunking
│       │   └── management/commands/
│       │       └── process_async_task.py  # Async task processor daemon
│       └── media/                   # Runtime media storage
│           ├── videos/              # Uploaded video files
│           ├── audio/               # Extracted WAV files
│           ├── thumbnails/          # Generated thumbnail images
│           └── streams/             # HLS streaming segments
│
├── frontend/
│   ├── package.json                 # React app dependencies (pnpm)
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── src/
│       ├── index.tsx                # App entry point
│       ├── MainLayout.tsx           # Routing + sidebar layout
│       ├── config.ts                # API prefix, supported LLM models
│       ├── model.tsx                # TypeScript interfaces
│       ├── page/
│       │   ├── UploadDashboard.tsx   # Video upload with drag-and-drop
│       │   ├── VideoDashboard.tsx    # Video library grid
│       │   ├── CourseDashboard.tsx   # Course/episode management
│       │   ├── TaskDashboard.tsx     # Async task monitoring
│       │   └── LectureVideoAnalysis.tsx  # Main analysis page
│       └── components/
│           ├── ChatPanel.tsx         # Chat UI component
│           ├── ThinkingPanel.tsx     # AI reasoning visualization
│           └── lecture/
│               ├── StreamVideo.tsx       # HLS video player
│               ├── LectureTranscripts.tsx # Transcript viewer
│               ├── LectureSections.tsx    # Section/chapter viewer
│               ├── LectureChatbot.tsx     # Lecture Q&A chatbot
│               └── CourseCreationModal.tsx
│
├── doc/                             # Documentation (architecture, design docs)
└── screenshot/                      # UI screenshots
```

---

## Getting Started

### Prerequisites

- Python 3.10+ with conda or virtualenv
- Node.js 18+ with pnpm
- FFmpeg installed system-wide
- Alibaba Cloud DashScope API key (for ASR)
- Tencent Cloud COS credentials (for audio file hosting)

### Environment Setup

1. **Clone and configure environment variables**:
```bash
git clone <repo-url>
cd PolyU-Video-Agent
cp .env.example .env
# Edit .env with your API keys:
#   DASHSCOPE_API_KEY=your_dashscope_key
#   COS_SECRECT_ID=your_cos_secret_id
#   COS_SECRECT_KEY=your_cos_secret_key
#   COS_REGION=ap-singapore
#   COS_BUCKET=your_bucket_name
```

2. **Backend setup**:
```bash
cd server
conda env create -f environment.yml    # or: pip install -r requirements.txt
conda activate polyu-video
cd app
python manage.py migrate
python manage.py runserver             # Start API server on :8000
```

3. **Start the async task processor** (separate terminal):
```bash
cd server/app
python manage.py process_async_task    # Polls for pending tasks every 5s
```

4. **Frontend setup**:
```bash
cd frontend
pnpm install
pnpm start                             # Start dev server on :3000
```

5. Open `http://localhost:3000` in your browser.

---

## API Reference

All endpoints are prefixed with `/api/`.

### Videos

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/videos/` | List all videos |
| `POST` | `/api/videos/upload/` | Upload video (multipart/form-data) |
| `GET` | `/api/videos/<uuid>/` | Get video details |
| `PATCH` | `/api/videos/update/<uuid>/` | Update video metadata |
| `DELETE` | `/api/videos/delete/<uuid>/` | Delete video and related data |
| `GET` | `/api/videos/<uuid>/thumbnails/` | List thumbnails for a video |
| `GET` | `/api/videos/<uuid>/transcript/` | Get ASR transcript with sentences |
| `POST` | `/api/videos/process/` | Trigger async processing pipeline |

### Episodes (Courses)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/episodes/` | List all episodes |
| `POST` | `/api/episodes/new/` | Create new episode |
| `GET` | `/api/episodes/<uuid>/` | Get episode with nested videos |
| `PATCH` | `/api/episodes/update/<uuid>/` | Update episode |
| `DELETE` | `/api/episodes/delete/<uuid>/` | Delete episode |

### Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/tasks/video/<uuid>/` | List tasks for a video |
| `POST` | `/api/tasks/new/` | Create a task manually |
| `GET` | `/api/tasks/<uuid>/` | Get task details |

### Planned Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/videos/<uuid>/sections/` | Get video sections/chapters |
| `GET` | `/api/videos/<uuid>/summary/` | Get AI-generated summary |
| `GET` | `/api/videos/<uuid>/knowledge/` | Get knowledge points |
| `GET` | `/api/videos/<uuid>/mindmap/` | Get knowledge mindmap data |
| `POST` | `/api/chat/` | Create a chat session |
| `POST` | `/api/chat/<uuid>/message/` | Send message to chatbot |
| `GET` | `/api/chat/<uuid>/messages/` | Get chat history |
| `GET` | `/api/health/` | Server health check |

---

## Data Models

```
Episode (course/lecture series)
  └── Video (uploaded lecture video)
        ├── Thumbnail (slide screenshots at transition points)
        ├── VideoTranscript (ASR metadata, 1:1)
        │     └── TranscriptSentence (timestamped sentences)
        ├── AsyncTaskItem (processing pipeline tasks, DAG)
        │
        │  --- Planned ---
        ├── VideoSection (thematic chapter boundaries)
        ├── KnowledgePoint (fine-grained knowledge entries)
        ├── KnowledgeSummary (coarse-grained summaries)
        ├── KnowledgeMindmap (hierarchical concept map)
        └── ChatSession
              └── ChatMessage
```

---

## Async Task Pipeline

The system uses a custom DAG-based async task processor (`python manage.py process_async_task`) that:

- **Polls** the database every 5 seconds for pending tasks
- **Resolves dependencies** via the `previous` field (task chaining)
- **Uses row-level locking** (`SELECT FOR UPDATE SKIP LOCKED`) for safe concurrent processing
- **Chains outputs** -- a completed task's result JSON is merged into the next task's input
- **Handles errors** in isolation without blocking sibling tasks
- **Supports graceful shutdown** via SIGINT/SIGTERM

### Current Task DAG

```
Upload Video
     │
     ├──→ Task 1: ASR Transcription ──────────────┐
     │    (extract audio → COS upload → Qwen-ASR)  │  No dependencies
     │                                              │  between 1, 2, 3
     ├──→ Task 2: HLS Encoding ────────────────────┤
     │    (multi-resolution transcoding)            │
     │                                              │
     └──→ Task 3: SSIM Slide Detection ────────────┘
          (frame change detection)
               │
               └──→ Task 4: Thumbnail Generation
                    (extract frames at slide changes)
                         │
                         └──→ Task 5: AI Summary (stub)
                              (planned: LLM-powered summarization)
```

---

## Roadmap

See [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md) for the detailed architecture design and phased development plan.

---

## License

Apache License 2.0 -- see [LICENSE](LICENSE) for details.
