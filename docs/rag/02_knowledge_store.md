# Knowledge Store — Vector Database Design

## Overview

The knowledge store is the retrieval backbone of the RAG system. It uses ChromaDB as an embedded vector database with sentence-transformers for dense embedding generation. All lecture content is embedded and indexed during the async task pipeline, then queried at chat time.

## Component: `VectorStore` (vector_store.py)

### Initialization (Lazy)

The vector store initializes on first use, not at import time:

```python
store = get_vector_store()  # singleton
store.query(...)             # triggers _ensure_initialized() on first call
```

Initialization steps:
1. Create `media/chromadb/` directory (persistent storage)
2. Create `PersistentClient` with cosine distance metric
3. Get or create the `lecture_knowledge` collection
4. Load `all-MiniLM-L6-v2` sentence-transformers model on CPU

### Configuration

| Setting | Default | Env Var | Description |
|---------|---------|---------|-------------|
| Persist directory | `./media/chromadb` | `CHROMA_PERSIST_DIR` | On-disk ChromaDB path |
| Collection name | `lecture_knowledge` | — | HNSW collection name |
| Embedding model | `all-MiniLM-L6-v2` | — | Sentence-transformers model |
| Distance metric | cosine | — | `hnsw:space` config |
| Device | cpu | — | Torch device for encoding |

### Embedding Model: all-MiniLM-L6-v2

| Property | Value |
|----------|-------|
| Architecture | 6-layer MiniLM (distilled BERT) |
| Output dimensions | 384 |
| Model size | ~80 MB |
| Max sequence length | 256 tokens |
| Language | English (primary), multilingual support basic |
| Speed (CPU) | ~100 texts/sec for short texts |
| Memory | ~200 MB when loaded |

### Document Types in the Store

Documents are stored with metadata that enables filtered retrieval:

#### 1. Knowledge Points (`type: "knowledge_point"`)

Embedded during `task_embed_knowledge` from `KnowledgePoint` records.

```
Embed text: "{title}: {summary} (Key terms: {term1}, {term2})"
```

Metadata:
```json
{
  "video_id": "uuid",
  "section_id": "uuid",
  "type": "knowledge_point",
  "title": "Gradient Descent Basics",
  "begin_time": 120.5,
  "end_time": 180.0,
  "importance": 0.85
}
```

#### 2. Section Transcripts (`type: "section_transcript"`)

Embedded during `task_embed_knowledge` from `VideoSection.transcript_text`.

```
Embed text: first 2000 characters of section transcript
```

Metadata:
```json
{
  "video_id": "uuid",
  "section_id": "uuid",
  "type": "section_transcript",
  "title": "Introduction to Neural Networks",
  "begin_time": 0.0,
  "end_time": 300.0
}
```

#### 3. Slide OCR Text (`type: "slide_ocr"`)

Embedded during `task_embed_knowledge` from `SlideOCR` records (extracted by `task_slides_ocr` using Qwen2.5-VL-72B-Instruct).

```
Embed text: first 2000 characters of OCR-extracted slide text
```

Metadata:
```json
{
  "video_id": "uuid",
  "section_id": "uuid",
  "type": "slide_ocr",
  "title": "Slide @ 02:15",
  "begin_time": 135.0,
  "end_time": 135.0
}
```

Each slide OCR record is matched to its containing section by time overlap (`begin_time <= time_second <= end_time`). This allows RAG queries to retrieve text visible on slides alongside spoken transcript content and extracted knowledge points.

### Key Operations

#### Upsert (Single)
```python
store.upsert(id="kp-uuid", text="...", metadata={...})
```
- Encodes text to 384-dim vector
- Cleans metadata (ChromaDB requires str/int/float/bool values)
- Upserts into collection

#### Upsert Batch
```python
count = store.upsert_batch(ids=[...], texts=[...], metadatas=[...], batch_size=100)
```
- Encodes in batches of 100 for memory efficiency
- Returns total upserted count

#### Query
```python
results = store.query(
    query_text="What is backpropagation?",
    video_id="uuid",           # optional: scope to single video
    content_type="knowledge_point",  # optional: filter by type
    top_k=5
)
```

Returns:
```python
[
    {
        "id": "kp-uuid",
        "text": "Backpropagation: The algorithm for computing gradients...",
        "metadata": {"title": "...", "begin_time": 120.5, ...},
        "distance": 0.23,      # cosine distance (0 = identical)
        "relevance": 0.77      # 1.0 - distance
    },
    ...
]
```

#### Cleanup
```python
store.delete_by_video("uuid")  # removes all docs for a video
store.reset()                   # wipes entire collection
```

### Data Lifecycle

```
Video Uploaded
     │
     ▼ (task pipeline)
task_embed_knowledge
  ├── delete_by_video(video_id)    ← clean previous embeddings
  ├── upsert_batch(knowledge_points)
  ├── upsert_batch(section_transcripts)
  ├── upsert_batch(slide_ocr_texts)
  └── update embedding_id references
     │
     ▼ (runtime queries)
RAGEngine._retrieve_context()     ← query(question, video_id, top_k=6)
     │
     ▼ (cleanup)
Video deletion                    ← delete_by_video(video_id)
```

### Storage Format

ChromaDB PersistentClient stores data in:
```
media/chromadb/
  chroma.sqlite3           # metadata + document text
  <uuid>/                  # HNSW index directory
    data_level0.bin
    header.bin
    length.bin
    link_lists.bin
```

Typical storage per video: 1-5 MB (depending on section count and transcript length).
