# Task: task_hybrid_chunking

## Overview

Segments the lecture video into meaningful sections by combining three signal sources: SSIM slide change timestamps, ASR transcript silence gaps, and (optionally) semantic similarity between adjacent text windows. Produces `VideoSection` records that serve as the foundation for subsequent knowledge extraction.

**Position in DAG:** Task 5 (depends on T4: task_generate_thumbnails; reads ASR data from database)

## Input

Receives the output of `task_generate_thumbnails` (which chains from SSIM):

```json
{
  "video_id": "uuid-string",
  "file": "videos/lecture1.mp4",
  "changes": [10.22, 34.56, 78.90, ...],
  "thumbnail_count": 15
}
```

Also reads the ASR transcript directly from the database (saved by T1 in a separate parallel branch).

## Output

```json
{
  "video_id": "uuid-string",
  "section_count": 8
}
```

## Algorithm

### Step 1: Collect Candidate Split Points

Two sources of candidates:

1. **Slide changes** from SSIM detection (from input `changes` array)
2. **Silence gaps** detected from ASR transcript -- gaps >= 2.0 seconds between consecutive sentences are identified, and the midpoint of each gap is used as a candidate

All candidates are merged and sorted.

### Step 2: Semantic Filtering (Optional)

If `use_semantic_check=True` (currently disabled for 8GB systems):

- Loads `all-MiniLM-L6-v2` sentence-transformers model (~80MB)
- For each candidate split point, extracts text windows before and after
- Computes cosine similarity between the two windows
- Rejects candidates where similarity > threshold (same topic continues)

**Currently disabled** (`use_semantic_check=False`) to reduce memory usage on constrained hardware.

### Step 3: Minimum Duration Enforcement

Candidates that are too close to the previous split (< `min_chunk_duration=30.0s`) are skipped.

### Step 4: Chunk Building

Final boundaries are constructed from filtered candidates + video start (0.0s) + video end (duration). Small trailing chunks are merged with their predecessors.

### Step 5: Section Creation

For each chunk `(start, end)`:
- Extracts the transcript text for that time range (from ASR sentences)
- Finds the closest thumbnail to the section start time
- Creates a `VideoSection` record with title `"Section N"` (later updated by LLM in T6)

## Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `min_chunk_duration` | 30.0s | Minimum section length |
| `silence_gap_threshold` | 2.0s | Silence gap to consider as split candidate |
| `semantic_similarity_threshold` | 0.5 | Topic shift detection threshold |
| `use_semantic_check` | False | Disabled for memory-constrained systems |

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `VideoSection` | Delete all existing for video + create new |
| `VideoTranscript` / `TranscriptSentence` | Read only (populated by T1) |
| `Thumbnail` | Read only (find closest for each section) |

## Duration Estimation

If `video.duration` is 0 (not explicitly set), the task estimates duration from:
1. The last slide change timestamp + 60s, or
2. The last transcript sentence end time + 10s, or
3. Fallback: 3600s (1 hour)
