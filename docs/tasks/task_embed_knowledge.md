# Task: task_embed_knowledge

## Overview

Generates dense vector embeddings for all knowledge points and section transcripts, then stores them in ChromaDB for semantic retrieval. This enables the RAG chatbot and agent to search lecture content by meaning rather than keywords.

**Position in DAG:** Task 7 (depends on T6: task_fine_grained_knowledge)

## Input

```json
{
  "video_id": "uuid-string",
  "knowledge_points_count": 24,
  "sections_processed": 7
}
```

## Output

```json
{
  "video_id": "uuid-string",
  "embedded_knowledge_points": 24,
  "embedded_sections": 7
}
```

## Processing Steps

### Step 1: Cleanup

All existing embeddings for this video are deleted from ChromaDB:

```python
store.delete_by_video(video_id)
```

### Step 2: Embed Knowledge Points

For each `KnowledgePoint` record:

1. Construct embed text: `"{title}: {summary} (Key terms: {term1}, {term2})"`
2. Encode using `all-MiniLM-L6-v2` sentence-transformers model (384-dimensional vectors)
3. Store in ChromaDB with metadata:

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

### Step 3: Embed Section Transcripts

For each `VideoSection` with transcript text >= 10 characters:

1. Use the first 2000 characters of transcript text
2. Encode and store with metadata type `"section_transcript"`

### Step 4: Update References

Sets `embedding_id` on each `KnowledgePoint` record to its ChromaDB document ID.

## Embedding Model

| Property | Value |
|----------|-------|
| Model | `all-MiniLM-L6-v2` |
| Dimensions | 384 |
| Size on disk | ~80 MB |
| Device | CPU only |
| Batch processing | Yes (batch_size=100) |

## ChromaDB Configuration

| Property | Value |
|----------|-------|
| Persist directory | `media/chromadb/` |
| Collection name | `lecture_knowledge` |
| Distance metric | Cosine |
| Client type | `PersistentClient` (on-disk) |

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `KnowledgePoint` | Read + bulk update `embedding_id` |
| `VideoSection` | Read only |

## Vector Store Operations

| Operation | Count |
|-----------|-------|
| `delete_by_video` | 1 (cleanup) |
| `upsert_batch` (KPs) | ceil(KP_count / 100) batches |
| `upsert_batch` (sections) | ceil(section_count / 100) batches |

## Memory Usage

The `all-MiniLM-L6-v2` model requires ~200MB RAM when loaded. It is loaded lazily (on first use) and kept as a singleton. Encoding 100 texts takes ~1-2 seconds on CPU.
