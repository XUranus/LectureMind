# LectureMind — Architecture & Development Plan

This document provides the detailed system architecture, AI feature design, and phased development plan for the LectureMind project.

---

## Table of Contents

1. [Current System State](#1-current-system-state)
2. [Architecture Overview](#2-architecture-overview)
3. [New Data Model Design](#3-new-data-model-design)
4. [Feature Design: Fine-Grained Knowledge Extraction](#4-feature-design-fine-grained-knowledge-extraction)
5. [Feature Design: Coarse-Grained Knowledge Summarization](#5-feature-design-coarse-grained-knowledge-summarization)
6. [Feature Design: RAG System](#6-feature-design-rag-system)
7. [Feature Design: Lecture Chatbot](#7-feature-design-lecture-chatbot)
8. [Feature Design: Knowledge Mindmap](#8-feature-design-knowledge-mindmap)
9. [LangGraph Agent Architecture](#9-langgraph-agent-architecture)
10. [Frontend Feature Design](#10-frontend-feature-design)
11. [Development Plan](#11-development-plan)
12. [Technical Decisions](#12-technical-decisions)

---

## 1. Current System State

### What's Working
- Video upload, CRUD, course/episode management
- HLS multi-resolution adaptive streaming (4 renditions)
- ASR transcription via DashScope Qwen3-ASR (sentence-level, with timestamps/emotions)
- SSIM-based slide transition detection (multithreaded)
- Thumbnail generation at slide change points
- DAG-based async task pipeline with dependency resolution
- Frontend: video player, transcript viewer with seek, task monitoring

### What Exists But Isn't Integrated
- **Hybrid chunker** (`lecture_video_hybrid_chunker.py`): Combines slide detection + silence gaps + sentence-transformers semantic similarity. Code complete, not wired into task pipeline.
- **ChatPanel component**: Full-featured chat UI from prior work. Not connected to any backend.
- **ThinkingPanel component**: AI reasoning step visualization. Not used.
- **LectureSections component**: Section viewer with mock data. No backend endpoint.
- **Summary task**: Registered in pipeline but returns placeholder text.

### Key Gaps to Fill
1. No sections/chapters API or model
2. No knowledge extraction (fine-grained or coarse-grained)
3. No vector database or embedding pipeline
4. No LLM integration for summarization or chat
5. No RAG query system
6. No mindmap data model or generation
7. No health check endpoint
8. Frontend chatbot is an echo stub

---

## 2. Architecture Overview

### Component Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                              │
│                                                                      │
│   ┌────────────┐  ┌───────────┐  ┌──────────┐  ┌────────────────┐   │
│   │ Video      │  │ Knowledge │  │ Chat     │  │ Mindmap        │   │
│   │ Analysis   │  │ Explorer  │  │ Panel    │  │ Viewer         │   │
│   │ Page       │  │ Panel     │  │ (SSE)    │  │ (D3/ReactFlow) │   │
│   └─────┬──────┘  └─────┬─────┘  └────┬─────┘  └──────┬─────────┘   │
│         │               │              │               │             │
│         └───────────────┴──────────────┴───────────────┘             │
│                              │ REST + SSE                            │
└──────────────────────────────┼────────────────────────────────────────┘
                               │
┌──────────────────────────────┼────────────────────────────────────────┐
│                     BACKEND (Django)     │                            │
│                                          │                            │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                   REST API Layer (DRF)                        │    │
│  │                                                               │    │
│  │  Video API │ Section API │ Knowledge API │ Chat API │ Mindmap │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              Async Task Pipeline (DAG Executor)               │    │
│  │                                                               │    │
│  │  Phase 1: Preprocessing                                       │    │
│  │    ASR ─┐                                                     │    │
│  │    HLS ─┤ (parallel)                                          │    │
│  │   SSIM ─┘──→ Thumbnails                                      │    │
│  │                                                               │    │
│  │  Phase 2: Knowledge Extraction                                │    │
│  │    Hybrid Chunking ──→ Fine-Grained KP ──→ Coarse-Grained    │    │
│  │                              │                    │            │    │
│  │                              ▼                    ▼            │    │
│  │                         Vector DB            Mindmap Gen      │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    AI Service Layer                            │    │
│  │                                                               │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │    │
│  │  │  LLM Client  │  │  Embedding   │  │  LangGraph Agent │   │    │
│  │  │  (Qwen API)  │  │  Service     │  │  Orchestrator    │   │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │    │
│  │                                                               │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │    │
│  │  │  ASR Client  │  │  Vector DB   │  │  Prompt          │   │    │
│  │  │  (DashScope) │  │  (ChromaDB)  │  │  Templates       │   │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘   │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    Storage Layer                               │    │
│  │  SQLite/PostgreSQL │ ChromaDB │ Tencent COS │ Local Media FS  │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Data Flow: End-to-End

```
User uploads video
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Phase 1: Preprocessing (existing)                    │
│                                                      │
│  Video ──→ SSIM Detection ──→ Slide timestamps       │
│        ──→ Audio Extract ──→ ASR ──→ Transcript      │
│        ──→ HLS Encoding ──→ Streaming files          │
│        ──→ Thumbnails at slide changes               │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ Phase 2: Intelligent Segmentation (new)              │
│                                                      │
│  Slide timestamps ─┐                                 │
│  ASR transcript ────┤──→ Hybrid Chunker ──→ Sections │
│  Silence gaps ──────┘    (slide + silence + semantic) │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ Phase 3: Fine-Grained Knowledge (new)                │
│                                                      │
│  For each section:                                   │
│    Slide image + Transcript text                     │
│         │                                            │
│         ▼                                            │
│    Multimodal LLM (Qwen-VL or Qwen-turbo)           │
│         │                                            │
│         ├──→ Knowledge points (title, summary, terms)│
│         ├──→ Dense embedding ──→ Vector DB           │
│         └──→ Section summary                         │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ Phase 4: Coarse-Grained Knowledge (new)              │
│                                                      │
│  All fine-grained knowledge points                   │
│         │                                            │
│         ▼                                            │
│    LLM aggregation                                   │
│         │                                            │
│         ├──→ Thematic chapters                       │
│         ├──→ Lecture-level summary                   │
│         ├──→ Concept hierarchy ──→ Mindmap JSON      │
│         └──→ Cross-references                        │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│ Phase 5: RAG + Chatbot (new)                         │
│                                                      │
│  User query                                          │
│       │                                              │
│       ▼                                              │
│  Embedding ──→ Vector search ──→ Top-K segments      │
│                                       │              │
│                                       ▼              │
│                              LLM with context        │
│                              (transcript + slide +   │
│                               knowledge points)      │
│                                       │              │
│                                       ▼              │
│                              Answer with citations   │
│                              + timestamp references  │
└─────────────────────────────────────────────────────┘
```

---

## 3. New Data Model Design

### VideoSection

Represents an intelligent segment/chapter of a video produced by the hybrid chunker.

```python
class VideoSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=512, blank=True)          # AI-generated section title
    begin_time = models.FloatField(help_text="Start time in seconds")
    end_time = models.FloatField(help_text="End time in seconds")
    transcript_text = models.TextField(blank=True)                 # Concatenated transcript for this section
    thumbnail = models.ForeignKey(Thumbnail, null=True, on_delete=models.SET_NULL)  # Representative slide
    order = models.IntegerField(default=0)                         # Section ordering

    class Meta:
        ordering = ['order', 'begin_time']
        indexes = [models.Index(fields=['video', 'begin_time'])]
```

### KnowledgePoint

Fine-grained knowledge extracted from a single section.

```python
class KnowledgePoint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    section = models.ForeignKey(VideoSection, on_delete=models.CASCADE, related_name='knowledge_points')
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='knowledge_points')
    title = models.CharField(max_length=512)                       # Knowledge point title
    summary = models.TextField()                                    # Detailed explanation
    key_terms = models.JSONField(default=list)                     # ["term1", "term2", ...]
    importance = models.FloatField(default=0.5)                    # 0.0 - 1.0 importance score
    embedding_id = models.CharField(max_length=255, blank=True)    # Reference to vector DB entry
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['section__begin_time']
```

### KnowledgeSummary

Coarse-grained, lecture-level knowledge aggregation.

```python
class KnowledgeSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name='knowledge_summary')
    overall_summary = models.TextField()                            # Full lecture summary
    chapter_outline = models.JSONField(default=list)               # [{title, begin_time, end_time, summary}]
    key_concepts = models.JSONField(default=list)                  # ["concept1", "concept2", ...]
    learning_objectives = models.JSONField(default=list)           # ["objective1", ...]
    difficulty_level = models.CharField(max_length=20, blank=True) # beginner/intermediate/advanced
    created_at = models.DateTimeField(auto_now_add=True)
```

### KnowledgeMindmap

Hierarchical concept map for visualization.

```python
class KnowledgeMindmap(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name='mindmap')
    mindmap_data = models.JSONField()                              # Hierarchical node/edge JSON
    format_version = models.CharField(max_length=10, default='1.0')
    created_at = models.DateTimeField(auto_now_add=True)
```

**Mindmap JSON schema:**
```json
{
  "root": {
    "id": "root",
    "label": "Lecture: Introduction to Machine Learning",
    "children": [
      {
        "id": "ch1",
        "label": "Supervised Learning",
        "time_range": [0, 600],
        "children": [
          {"id": "kp1", "label": "Linear Regression", "time_range": [60, 180]},
          {"id": "kp2", "label": "Classification", "time_range": [180, 360]}
        ]
      },
      {
        "id": "ch2",
        "label": "Unsupervised Learning",
        "time_range": [600, 1200],
        "children": [...]
      }
    ]
  }
}
```

### ChatSession & ChatMessage

For the RAG-powered chatbot.

```python
class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=255, blank=True)
    model_name = models.CharField(max_length=100, default='qwen2.5-7b-instruct')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class ChatMessage(models.Model):
    ROLE_CHOICES = [('user', 'User'), ('assistant', 'Assistant'), ('system', 'System')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    sources = models.JSONField(default=list, blank=True)  # [{section_id, time, relevance_score}]
    thinking_steps = models.JSONField(default=list, blank=True)  # For reasoning trace display
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
```

---

## 4. Feature Design: Fine-Grained Knowledge Extraction

### Overview

For each video section (produced by hybrid chunking), extract structured knowledge by feeding the section's slide image + transcript text to a multimodal LLM.

### Task Implementation

```python
# New async task: task_hybrid_chunking
# Depends on: task_ssim_move_detection (needs slide timestamps)
#             task_extract_audio_and_transcript (needs transcript)
# Produces: VideoSection records

def task_hybrid_chunking(input_data):
    """
    Combine SSIM slide changes + ASR transcript to produce
    intelligent video sections using the hybrid chunker.
    """
    video_id = input_data['video_id']
    slide_changes = input_data['changes']     # from SSIM task
    transcript = fetch_transcript(video_id)    # from DB

    sections = hybrid_chunk(
        slide_change_times=slide_changes,
        asr_transcript=transcript,
        min_chunk_duration=30.0,
        semantic_threshold=0.5
    )

    # Save VideoSection records
    for i, (start, end) in enumerate(sections):
        VideoSection.objects.create(
            video_id=video_id,
            begin_time=start,
            end_time=end,
            order=i,
            transcript_text=extract_transcript_for_range(transcript, start, end)
        )

    return {"video_id": video_id, "section_count": len(sections)}
```

```python
# New async task: task_fine_grained_knowledge
# Depends on: task_hybrid_chunking

def task_fine_grained_knowledge(input_data):
    """
    For each section, call LLM with slide image + transcript
    to extract knowledge points.
    """
    video_id = input_data['video_id']
    sections = VideoSection.objects.filter(video_id=video_id)

    for section in sections:
        # 1. Get the slide thumbnail for this section
        slide_image = get_slide_image_for_section(section)

        # 2. Construct prompt
        prompt = FINE_GRAINED_EXTRACTION_PROMPT.format(
            transcript=section.transcript_text,
            time_range=f"{section.begin_time}s - {section.end_time}s"
        )

        # 3. Call LLM (with image if multimodal, text-only otherwise)
        response = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            model="qwen2.5-7b-instruct"
        )

        # 4. Parse structured output
        knowledge = parse_knowledge_response(response)

        # 5. Save knowledge points
        for kp in knowledge['points']:
            point = KnowledgePoint.objects.create(
                section=section,
                video_id=video_id,
                title=kp['title'],
                summary=kp['summary'],
                key_terms=kp['terms'],
                importance=kp.get('importance', 0.5)
            )

            # 6. Generate embedding and store in vector DB
            embedding = embedding_service.encode(
                f"{kp['title']}: {kp['summary']}"
            )
            vector_db.upsert(
                id=str(point.id),
                embedding=embedding,
                metadata={
                    "video_id": video_id,
                    "section_id": str(section.id),
                    "begin_time": section.begin_time,
                    "end_time": section.end_time,
                    "title": kp['title'],
                    "type": "knowledge_point"
                }
            )
            point.embedding_id = str(point.id)
            point.save()

        # 7. Generate section title
        section.title = knowledge.get('section_title', f'Section {section.order + 1}')
        section.save()

    return {"video_id": video_id, "knowledge_points_count": KnowledgePoint.objects.filter(video_id=video_id).count()}
```

### Prompt Template (Fine-Grained)

```
You are an expert educational content analyst. Analyze the following lecture segment
and extract structured knowledge points.

Time range: {time_range}

Transcript:
---
{transcript}
---

Extract the following in JSON format:
{
  "section_title": "A concise title for this lecture segment",
  "points": [
    {
      "title": "Knowledge point title",
      "summary": "2-3 sentence explanation of this concept",
      "terms": ["key term 1", "key term 2"],
      "importance": 0.0-1.0
    }
  ]
}

Rules:
- Extract 1-5 knowledge points per segment
- Each point should be self-contained and understandable
- Key terms should be specific technical vocabulary
- Importance reflects how central the concept is to the lecture
```

---

## 5. Feature Design: Coarse-Grained Knowledge Summarization

### Overview

Aggregate all fine-grained knowledge points into a lecture-level summary with thematic chapters, key concepts, and learning objectives.

### Task Implementation

```python
# New async task: task_coarse_grained_knowledge
# Depends on: task_fine_grained_knowledge

def task_coarse_grained_knowledge(input_data):
    video_id = input_data['video_id']
    sections = VideoSection.objects.filter(video_id=video_id).prefetch_related('knowledge_points')

    # 1. Gather all fine-grained knowledge
    all_knowledge = []
    for section in sections:
        section_data = {
            "title": section.title,
            "time_range": f"{section.begin_time}-{section.end_time}",
            "points": [
                {"title": kp.title, "summary": kp.summary, "terms": kp.key_terms}
                for kp in section.knowledge_points.all()
            ]
        }
        all_knowledge.append(section_data)

    # 2. Call LLM for aggregation
    prompt = COARSE_GRAINED_PROMPT.format(
        knowledge_json=json.dumps(all_knowledge, indent=2)
    )
    response = llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        model="qwen2.5-7b-instruct"
    )

    # 3. Parse and save
    result = parse_coarse_grained_response(response)

    KnowledgeSummary.objects.update_or_create(
        video_id=video_id,
        defaults={
            "overall_summary": result['summary'],
            "chapter_outline": result['chapters'],
            "key_concepts": result['concepts'],
            "learning_objectives": result['objectives'],
            "difficulty_level": result.get('difficulty', 'intermediate')
        }
    )

    # 4. Also embed the lecture summary for RAG
    embedding = embedding_service.encode(result['summary'])
    vector_db.upsert(
        id=f"summary-{video_id}",
        embedding=embedding,
        metadata={
            "video_id": video_id,
            "type": "lecture_summary",
            "title": sections.first().video.title if sections.exists() else ""
        }
    )

    return {"video_id": video_id, "chapters": len(result['chapters'])}
```

### Prompt Template (Coarse-Grained)

```
You are an expert educational content analyst. Given the fine-grained knowledge points
extracted from a lecture video, produce a comprehensive lecture-level analysis.

Fine-Grained Knowledge:
---
{knowledge_json}
---

Produce the following in JSON format:
{
  "summary": "A comprehensive 3-5 paragraph summary of the entire lecture",
  "chapters": [
    {
      "title": "Chapter title",
      "begin_time": 0.0,
      "end_time": 600.0,
      "summary": "1-2 sentence chapter summary",
      "key_points": ["point1", "point2"]
    }
  ],
  "concepts": ["Concept 1", "Concept 2", ...],
  "objectives": ["After this lecture, students should be able to..."],
  "difficulty": "beginner|intermediate|advanced"
}

Rules:
- Group related sections into 3-7 thematic chapters
- The summary should capture the lecture's narrative arc
- Concepts should be ordered from foundational to advanced
- Learning objectives should be actionable and measurable
```

---

## 6. Feature Design: RAG System

### Overview

The RAG (Retrieval-Augmented Generation) system enables semantic search over lecture content and provides grounded answers to user queries.

### Components

#### 6.1 Vector Database (ChromaDB)

ChromaDB is recommended for the initial implementation due to:
- Runs embedded (no separate server needed), simple Python API
- Supports persistent storage, metadata filtering
- Native support for sentence-transformers
- Easy migration path to Milvus/Qdrant for production scale

```python
# server/app/api/vector_store.py

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

class VectorStore:
    def __init__(self, persist_dir="./media/chromadb", collection_name="lecture_knowledge"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')

    def upsert(self, id: str, text: str, metadata: dict):
        embedding = self.encoder.encode(text).tolist()
        self.collection.upsert(
            ids=[id],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[text]
        )

    def query(self, query_text: str, video_id: str = None, top_k: int = 5):
        query_embedding = self.encoder.encode(query_text).tolist()
        where_filter = {"video_id": video_id} if video_id else None
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        return results

    def delete_by_video(self, video_id: str):
        """Delete all entries for a video (cleanup on video deletion)."""
        self.collection.delete(where={"video_id": video_id})
```

#### 6.2 Embedding Pipeline

What gets embedded and stored in the vector DB:

| Content Type | Source | Granularity | Metadata |
|---|---|---|---|
| Transcript sentences | ASR output | Sentence-level | video_id, begin_time, end_time, language |
| Knowledge point summaries | Fine-grained extraction | Per-knowledge-point | video_id, section_id, title, terms |
| Section summaries | Fine-grained titles | Per-section | video_id, begin_time, end_time |
| Lecture summary | Coarse-grained | Per-video | video_id, title, concepts |

#### 6.3 RAG Query Pipeline

```python
# server/app/api/rag_engine.py

class RAGEngine:
    def __init__(self, vector_store, llm_client):
        self.vector_store = vector_store
        self.llm_client = llm_client

    def query(self, question: str, video_id: str, top_k: int = 5) -> dict:
        # 1. Retrieve relevant segments
        results = self.vector_store.query(
            query_text=question,
            video_id=video_id,
            top_k=top_k
        )

        # 2. Build context from retrieved segments
        context_parts = []
        sources = []
        for doc, metadata, distance in zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        ):
            context_parts.append(f"[{metadata.get('title', 'Segment')}] "
                                f"(t={metadata.get('begin_time', '?')}s): {doc}")
            sources.append({
                "title": metadata.get('title', ''),
                "begin_time": metadata.get('begin_time'),
                "end_time": metadata.get('end_time'),
                "relevance": 1 - distance,  # cosine distance to similarity
                "type": metadata.get('type', 'unknown')
            })

        context = "\n\n".join(context_parts)

        # 3. Generate grounded answer
        prompt = RAG_ANSWER_PROMPT.format(
            context=context,
            question=question
        )
        answer = self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            model="qwen2.5-7b-instruct"
        )

        return {
            "answer": answer,
            "sources": sources
        }
```

### RAG Prompt Template

```
You are an expert teaching assistant. Answer the student's question using ONLY
the lecture content provided below. If the answer cannot be found in the context,
say so honestly.

Lecture Context:
---
{context}
---

Student's Question: {question}

Instructions:
- Base your answer strictly on the provided lecture content
- Reference specific timestamps when mentioning lecture segments (e.g., "at 5:30")
- If multiple segments are relevant, synthesize information across them
- Use clear, educational language appropriate for the lecture's level
- If the question is ambiguous, address the most likely interpretation
```

---

## 7. Feature Design: Lecture Chatbot

### Overview

The chatbot is the user-facing interface to the RAG system. It supports multi-turn conversations about a specific video's content.

### Backend API

```python
# POST /api/chat/
# Create a new chat session for a video
{
    "video_id": "uuid",
    "model_name": "qwen2.5-7b-instruct"  // optional
}
# Returns: {"id": "session-uuid", "video_id": "...", "created_at": "..."}

# POST /api/chat/<session_id>/message/
# Send a message and get AI response (SSE streaming)
{
    "content": "What is gradient descent?"
}
# Returns SSE stream:
# data: {"type": "thinking", "step": "Searching knowledge base..."}
# data: {"type": "thinking", "step": "Found 3 relevant segments"}
# data: {"type": "sources", "sources": [{...}]}
# data: {"type": "content", "delta": "Gradient"}
# data: {"type": "content", "delta": " descent"}
# data: {"type": "content", "delta": " is..."}
# data: {"type": "done", "message_id": "uuid"}

# GET /api/chat/<session_id>/messages/
# Get chat history
# Returns: [{"id": "uuid", "role": "user/assistant", "content": "...", "sources": [...]}]
```

### Streaming Response Implementation

```python
# server/app/api/views.py

from django.http import StreamingHttpResponse
import json

class ChatMessageView(generics.GenericAPIView):
    def post(self, request, session_id):
        session = get_object_or_404(ChatSession, id=session_id)
        user_content = request.data.get('content', '')

        # Save user message
        ChatMessage.objects.create(
            session=session, role='user', content=user_content
        )

        def event_stream():
            # Step 1: Signal thinking
            yield f"data: {json.dumps({'type': 'thinking', 'step': 'Searching lecture knowledge base...'})}\n\n"

            # Step 2: RAG retrieval
            rag_result = rag_engine.query(
                question=user_content,
                video_id=str(session.video_id)
            )

            yield f"data: {json.dumps({'type': 'sources', 'sources': rag_result['sources']})}\n\n"

            # Step 3: Stream LLM response
            full_response = ""
            for token in llm_client.stream_chat(...):
                full_response += token
                yield f"data: {json.dumps({'type': 'content', 'delta': token})}\n\n"

            # Step 4: Save assistant message
            msg = ChatMessage.objects.create(
                session=session,
                role='assistant',
                content=full_response,
                sources=rag_result['sources']
            )

            yield f"data: {json.dumps({'type': 'done', 'message_id': str(msg.id)})}\n\n"

        return StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
```

### Frontend Integration

The existing `ChatPanel.tsx` and `LectureChatbot.tsx` components provide the UI foundation. Key changes needed:

1. **LectureChatbot.tsx**: Replace echo logic with SSE connection to `/api/chat/<session_id>/message/`
2. **ThinkingPanel.tsx**: Wire up to display `thinking` events from the SSE stream
3. **Source citations**: Render clickable source cards that seek the video to referenced timestamps
4. **Multi-turn context**: Send conversation history with each request (or let backend manage via session)

---

## 8. Feature Design: Knowledge Mindmap

### Overview

Generate a hierarchical concept map from the coarse-grained knowledge, visualized as an interactive tree/graph.

### Generation Pipeline

```python
# New async task: task_generate_mindmap
# Depends on: task_coarse_grained_knowledge

def task_generate_mindmap(input_data):
    video_id = input_data['video_id']

    # 1. Gather knowledge summary + all knowledge points
    summary = KnowledgeSummary.objects.get(video_id=video_id)
    sections = VideoSection.objects.filter(video_id=video_id).prefetch_related('knowledge_points')

    # 2. Build input for LLM
    knowledge_structure = {
        "lecture_title": Video.objects.get(id=video_id).title,
        "chapters": summary.chapter_outline,
        "sections": [
            {
                "title": s.title,
                "time_range": [s.begin_time, s.end_time],
                "knowledge_points": [
                    {"title": kp.title, "terms": kp.key_terms}
                    for kp in s.knowledge_points.all()
                ]
            }
            for s in sections
        ]
    }

    # 3. Generate mindmap via LLM
    prompt = MINDMAP_GENERATION_PROMPT.format(
        knowledge=json.dumps(knowledge_structure, indent=2)
    )
    response = llm_client.chat(
        messages=[{"role": "user", "content": prompt}],
        model="qwen2.5-7b-instruct"
    )
    mindmap_data = parse_mindmap_response(response)

    # 4. Save
    KnowledgeMindmap.objects.update_or_create(
        video_id=video_id,
        defaults={"mindmap_data": mindmap_data}
    )

    return {"video_id": video_id, "node_count": count_nodes(mindmap_data)}
```

### Frontend Visualization

Use **React Flow** or **D3.js** for interactive mindmap rendering:

- Tree layout with collapsible nodes
- Each node shows concept name, time range, and importance
- Click a node to seek video to the relevant timestamp
- Color coding by chapter/theme
- Zoom/pan for large maps
- Export as PNG/SVG

---

## 9. LangGraph Agent Architecture

### Overview

LangGraph orchestrates complex, multi-step AI reasoning for advanced queries that cannot be answered by simple RAG retrieval.

### Agent Design

```
┌─────────────────────────────────────────────────┐
│              LangGraph State Machine             │
│                                                   │
│  ┌──────────┐    ┌──────────────┐    ┌────────┐  │
│  │ Classify  │──→│ Route Query  │──→│Execute │  │
│  │ Intent    │    │              │    │ Tools  │  │
│  └──────────┘    └──────────────┘    └────┬───┘  │
│                                           │      │
│                    ┌──────────────────────┘       │
│                    │                              │
│            ┌───────┴───────┐                     │
│            │  Synthesize   │                     │
│            │  Response     │                     │
│            └───────────────┘                     │
└──────────────────────────────────────────────────┘

Available Tools:
├── search_knowledge(query, video_id) → RAG retrieval
├── get_section_detail(section_id) → Full section content
├── get_transcript_range(video_id, start, end) → Transcript slice
├── compare_concepts(concept_a, concept_b) → Concept comparison
├── summarize_range(video_id, start, end) → On-demand summary
└── get_mindmap(video_id) → Knowledge structure
```

### Query Types

| Type | Example | Agent Behavior |
|------|---------|----------------|
| **Factual** | "What is gradient descent?" | Direct RAG retrieval → answer |
| **Temporal** | "What was discussed between 10:00 and 15:00?" | Transcript range tool → summarize |
| **Comparative** | "How does SVM differ from random forest?" | Multi-segment retrieval → compare tool → synthesize |
| **Structural** | "Give me an outline of this lecture" | Mindmap tool → format as outline |
| **Meta** | "What are the prerequisites for this lecture?" | Knowledge summary tool → extract objectives |

### Implementation (Phase 5)

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

def build_lecture_agent(video_id, rag_engine, llm_client):
    """Build a LangGraph agent for lecture Q&A."""

    tools = [
        SearchKnowledgeTool(rag_engine, video_id),
        GetSectionDetailTool(video_id),
        GetTranscriptRangeTool(video_id),
        SummarizeRangeTool(video_id, llm_client),
    ]

    def classify_intent(state):
        # LLM classifies user query type
        ...

    def should_use_tools(state):
        # Decide if tools are needed or if we can answer directly
        ...

    def synthesize(state):
        # Final answer generation with all gathered context
        ...

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_intent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("synthesize", synthesize)

    graph.add_edge("classify", "tools")
    graph.add_conditional_edges("tools", should_use_tools, {True: "tools", False: "synthesize"})
    graph.add_edge("synthesize", END)

    graph.set_entry_point("classify")
    return graph.compile()
```

---

## 10. Frontend Feature Design

### 10.1 Enhanced LectureVideoAnalysis Page

The main analysis page (`/lecture/:videoId`) needs additional tabs/panels:

```
┌──────────────────────────────────────────────────────────────────┐
│  ┌──────────────────────────┐  ┌──────────────────────────────┐  │
│  │                          │  │  Tabs:                        │  │
│  │    Video Player (HLS)    │  │  [Transcript][Sections][Chat] │  │
│  │                          │  │  [Knowledge][Mindmap]         │  │
│  │                          │  │                               │  │
│  ├──────────────────────────┤  │  ┌─────────────────────────┐ │  │
│  │  Thumbnail Strip         │  │  │  Active Tab Content     │ │  │
│  │  (clickable, scrollable) │  │  │                         │ │  │
│  │                          │  │  │  ...                     │ │  │
│  └──────────────────────────┘  │  └─────────────────────────┘ │  │
│                                └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**New Tabs:**

1. **Sections Tab**: Replace mock data with real API data. Show chapter cards with title, time range, summary. Click to seek.
2. **Knowledge Tab**: Browse fine-grained knowledge points grouped by section. Expandable cards showing title, summary, key terms. Filter/search.
3. **Mindmap Tab**: Interactive concept map visualization (React Flow). Click nodes to seek video. Zoom/pan/collapse.
4. **Chat Tab**: Full chatbot with SSE streaming, source citations with timestamp links, thinking process visualization.

### 10.2 New Components Needed

| Component | Description |
|-----------|-------------|
| `LectureKnowledge.tsx` | Knowledge point browser with section grouping and search |
| `LectureMindmap.tsx` | Interactive mindmap using React Flow or D3 |
| `SourceCitation.tsx` | Clickable source reference card (timestamp, relevance score) |
| `KnowledgeCard.tsx` | Expandable card for a single knowledge point |
| `SectionCard.tsx` | Section summary card with time range and seek button |

### 10.3 State Management

The `LectureVideoAnalysis` page currently lifts state for video seek synchronization. This pattern should be extended:

- **Video seek callback**: Shared across all tabs so any component can seek the player
- **Active section tracking**: Highlight the current section/knowledge point as video plays
- **Chat context**: Current video timestamp can be sent as context in chat messages

---

## 11. Development Plan

### Phase 1: Foundation Completion (1-2 weeks)

**Goal**: Wire up existing code, fill gaps, establish patterns for new features.

| Task | Priority | Effort | Details |
|------|----------|--------|---------|
| 1.1 Health check endpoint | High | 2h | Add `GET /api/health/` returning server status |
| 1.2 Integrate hybrid chunker into pipeline | High | 1d | Wire `lecture_video_hybrid_chunker.py` as a new async task after SSIM + ASR |
| 1.3 Add VideoSection model + API | High | 1d | Model, serializer, view, URL for sections CRUD |
| 1.4 Replace sections mock data in frontend | High | 0.5d | Connect `LectureSections.tsx` to real `/api/videos/{id}/sections/` |
| 1.5 Set up LLM client abstraction | High | 1d | Create `llm_client.py` wrapping OpenAI-compatible API for Qwen models |
| 1.6 Set up ChromaDB vector store | Medium | 1d | Install chromadb, create `vector_store.py`, integrate with settings |
| 1.7 Fix task DAG for new dependencies | Medium | 0.5d | Hybrid chunking depends on both ASR and SSIM completing |

**Revised Task DAG after Phase 1:**
```
ASR ────────────────┐
HLS ────────────────┤ (parallel)
SSIM ──→ Thumbnails ┤
                    └──→ Hybrid Chunking ──→ (Phase 2 tasks)
```

Note: Hybrid Chunking depends on both ASR (transcript) and SSIM (slide timestamps). The current DAG only supports single `previous` dependency. **Options**:
- **Option A**: Make hybrid chunking depend on "last finishing" prerequisite by chaining: SSIM → Thumbnails → Hybrid Chunking, and having it also fetch transcript from DB (since ASR likely finishes first).
- **Option B**: Extend `AsyncTaskItem.previous` to support multiple dependencies (change from single UUID to JSON array of UUIDs). This is more correct but requires modifying the task executor.

Recommendation: Start with **Option A** (simpler), then refactor to **Option B** if the DAG becomes more complex.

---

### Phase 2: Fine-Grained Knowledge Extraction (2-3 weeks)

**Goal**: Extract structured knowledge from each video section.

| Task | Priority | Effort | Details |
|------|----------|--------|---------|
| 2.1 Add KnowledgePoint model + migration | High | 0.5d | Model as designed in Section 3 |
| 2.2 Implement `task_fine_grained_knowledge` | High | 2d | LLM-powered extraction per section |
| 2.3 Design and test prompt templates | High | 1d | Iterative prompt engineering with real lecture data |
| 2.4 Embedding pipeline for knowledge points | High | 1d | Encode knowledge points into ChromaDB |
| 2.5 Knowledge API endpoints | High | 1d | `GET /api/videos/{id}/knowledge/` |
| 2.6 Knowledge Explorer frontend component | Medium | 2d | `LectureKnowledge.tsx` with section grouping |
| 2.7 Section title generation | Medium | 0.5d | Use LLM to generate meaningful section titles |
| 2.8 Update task DAG | Medium | 0.5d | Add fine-grained task after hybrid chunking |

---

### Phase 3: Coarse-Grained Knowledge & Mindmap (2-3 weeks)

**Goal**: Aggregate knowledge into lecture-level insights and visual concept maps.

| Task | Priority | Effort | Details |
|------|----------|--------|---------|
| 3.1 Add KnowledgeSummary model + migration | High | 0.5d | Model as designed in Section 3 |
| 3.2 Implement `task_coarse_grained_knowledge` | High | 2d | LLM aggregation of fine-grained knowledge |
| 3.3 Summary API endpoints | High | 0.5d | `GET /api/videos/{id}/summary/` |
| 3.4 Add KnowledgeMindmap model | High | 0.5d | Model as designed in Section 3 |
| 3.5 Implement `task_generate_mindmap` | High | 2d | LLM-generated hierarchical concept map |
| 3.6 Mindmap API endpoint | High | 0.5d | `GET /api/videos/{id}/mindmap/` |
| 3.7 Mindmap frontend component | High | 3d | React Flow interactive visualization |
| 3.8 Summary display in frontend | Medium | 1d | Lecture overview panel with summary, objectives, difficulty |
| 3.9 Prompt engineering for mindmap quality | Medium | 1d | Ensure proper hierarchical structure |

---

### Phase 4: RAG System & Chatbot (2-3 weeks)

**Goal**: Enable intelligent Q&A over lecture content with source citations.

| Task | Priority | Effort | Details |
|------|----------|--------|---------|
| 4.1 Implement RAG engine | High | 2d | `rag_engine.py` with ChromaDB retrieval + LLM generation |
| 4.2 Add ChatSession/ChatMessage models | High | 0.5d | Models as designed in Section 3 |
| 4.3 Chat API endpoints with SSE streaming | High | 2d | Session CRUD + streaming message endpoint |
| 4.4 Embed transcript sentences | High | 1d | Batch embed ASR sentences into vector DB |
| 4.5 Connect LectureChatbot frontend to API | High | 2d | SSE client, streaming display, source citations |
| 4.6 Source citation component | Medium | 1d | Clickable cards with timestamp seek |
| 4.7 ThinkingPanel integration | Medium | 1d | Display RAG reasoning steps |
| 4.8 Multi-turn conversation context | Medium | 1d | Include conversation history in LLM calls |
| 4.9 Chat history persistence + UI | Low | 1d | List/resume previous chat sessions |

---

### Phase 5: LangGraph Agent Orchestration (3-4 weeks)

**Goal**: Advanced multi-step reasoning for complex queries.

| Task | Priority | Effort | Details |
|------|----------|--------|---------|
| 5.1 Install and configure LangGraph | High | 1d | Add to requirements, set up graph builder |
| 5.2 Implement agent tools | High | 2d | SearchKnowledge, GetSection, GetTranscript, Summarize |
| 5.3 Build state graph with intent classification | High | 3d | Query routing based on intent type |
| 5.4 Replace direct RAG calls with agent | Medium | 1d | Agent wraps RAG as one of its tools |
| 5.5 Multi-video queries | Medium | 2d | Query across all videos in a course |
| 5.6 Agent observability | Low | 1d | Log reasoning traces, expose in ThinkingPanel |

---

### Phase 6: Production Readiness (2-3 weeks)

**Goal**: Prepare for deployment.

| Task | Priority | Effort | Details |
|------|----------|--------|---------|
| 6.1 PostgreSQL migration | High | 1d | Replace SQLite for concurrent write support |
| 6.2 User authentication | High | 2d | Django auth + JWT tokens |
| 6.3 Docker Compose setup | High | 2d | Backend + frontend + ChromaDB containers |
| 6.4 Django admin registration | Medium | 0.5d | Register all models in admin.py |
| 6.5 Test suite | Medium | 3d | Unit tests for tasks, API tests, integration tests |
| 6.6 Rate limiting & security | Medium | 1d | API throttling, CORS tightening, input validation |
| 6.7 Production settings | Medium | 0.5d | SECRET_KEY, DEBUG=False, proper ALLOWED_HOSTS |
| 6.8 Error handling & logging | Medium | 1d | Consistent error responses, structured logging |
| 6.9 Performance optimization | Low | 2d | Query optimization, caching, pagination |

---

### Timeline Summary

```
Week 1-2:   Phase 1 - Foundation Completion
Week 3-5:   Phase 2 - Fine-Grained Knowledge
Week 5-7:   Phase 3 - Coarse-Grained & Mindmap
Week 7-9:   Phase 4 - RAG & Chatbot
Week 9-12:  Phase 5 - LangGraph Agent
Week 12-14: Phase 6 - Production Readiness
```

Total estimated duration: **12-14 weeks** for full feature completion.

Phases 2 and 3 have significant backend overlap but separate frontend work, so some parallelism is possible. Some Phase 4 work (chat UI) can begin during Phase 3.

---

## 12. Technical Decisions

### Vector Database: ChromaDB vs Alternatives

| Criteria | ChromaDB | Milvus | Qdrant | pgvector |
|----------|----------|--------|--------|----------|
| **Setup** | Embedded, zero-config | Requires separate server | Separate server or embedded | PostgreSQL extension |
| **Python API** | Excellent | Good | Good | Via SQLAlchemy |
| **Scale** | Small-medium | Large | Medium-large | Medium |
| **Dev Experience** | Best for prototyping | Production-grade | Modern, well-documented | Familiar if using PG |
| **Migration Path** | Easy to replace | — | — | Tied to PostgreSQL |

**Recommendation**: Start with **ChromaDB** (embedded mode) for development speed. Consider **Qdrant** or **pgvector** for production if PostgreSQL is adopted.

### LLM Integration: Local vs Remote

The system should support both modes via a unified client:

```python
class LLMClient:
    """Unified LLM client supporting local (HuggingFace) and remote (DashScope/OpenAI-compatible) models."""

    def __init__(self, model_name, api_base=None, api_key=None):
        self.model_name = model_name
        if api_base:
            # Remote mode: OpenAI-compatible API
            self.client = OpenAI(base_url=api_base, api_key=api_key)
        else:
            # Local mode: transformers pipeline
            self.pipeline = load_local_model(model_name)

    def chat(self, messages, **kwargs):
        ...

    def stream_chat(self, messages, **kwargs):
        ...
```

**Model recommendations by task:**
- **Knowledge extraction**: `qwen2.5-7b-instruct` (good quality/speed balance)
- **Summary generation**: `qwen2.5-7b-instruct` or `qwen-turbo` (needs longer context)
- **Chat/RAG**: `qwen2.5-7b-instruct` (streaming support important)
- **Mindmap generation**: `qwen2.5-7b-instruct` (structured JSON output)
- **Development/testing**: `qwen2.5-0.5b-instruct` (fast iteration)

### Embedding Model

- **Current**: `all-MiniLM-L6-v2` (already used in hybrid chunker)
- **Upgrade path**: `text-embedding-v3` via DashScope (better multilingual support for Chinese lectures)
- Keep embedding model consistent across all pipelines to ensure vector space compatibility.

### Task DAG Multi-Dependency

The current `AsyncTaskItem.previous` field supports only single-dependency chains. For Phase 2+, hybrid chunking needs both ASR and SSIM results. Options:

1. **Chain linearly**: SSIM → Thumbnails → HybridChunking (fetch ASR from DB). Simple but slower.
2. **Multiple previous**: Change `previous` to `JSONField(default=list)` storing multiple UUIDs. Modify task executor to check all are `done`. More correct.
3. **Barrier task**: Insert a no-op "barrier" task that depends on ASR but does nothing, then HybridChunking depends on both barrier and Thumbnails.

**Recommendation**: Option 2 is the cleanest. The task executor change is minimal — query all UUIDs in the list and verify all have status `done`.

---

*This document should be updated as implementation progresses and design decisions are finalized.*
