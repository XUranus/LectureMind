# Async Task Pipeline Documentation

This directory contains detailed documentation for each async processing task in the LectureMind video analysis pipeline.

## Pipeline Overview

When a video is uploaded and processing is triggered via `POST /api/videos/process/`, a directed acyclic graph (DAG) of 9 tasks is created and executed by the async task processor (`python manage.py process_async_task`).

### Task DAG

```
  T1: task_extract_audio_and_transcript  ─┐
  T2: task_hls_streaming                  ├── (parallel, no dependencies)
  T3: task_ssim_move_detection           ─┘
                                           │
                T3 ─────────────────────> T4: task_generate_thumbnails
                                           │
                T4 ─────────────────────> T5: task_hybrid_chunking
                                           │
                T5 ─────────────────────> T6: task_fine_grained_knowledge
                                           │
                T6 ─────────────────────> T7: task_embed_knowledge
                                           │
                T7 ─────────────────────> T8: task_coarse_grained_summary
                                           │
                T8 ─────────────────────> T9: task_generate_mindmap
```

**Key points:**
- T1, T2, T3 run in parallel with no dependencies
- T4 depends on T3 (needs slide change timestamps)
- T5 depends on T4 (needs thumbnails) and reads ASR transcript from database (T1 must be complete)
- T6-T9 form a sequential chain for AI-powered analysis

### Task Processor

The task processor is a Django management command that:
- Polls the database every 5 seconds for pending tasks with satisfied dependencies
- Uses `SELECT FOR UPDATE SKIP LOCKED` for concurrent worker safety
- Chains task outputs: a completed task's result JSON is fed as input to its dependent task
- Handles cascade failures: if a task fails, all downstream dependents are automatically marked as `error` with `CascadeFailure` error type
- Supports retry: failed tasks can be reset to `pending` via the REST API, which also resets all cascade-blocked downstream tasks
- Loads `.env` on startup for API credentials

### Retry Mechanism

Failed tasks can be retried via:
- `POST /api/tasks/<uuid>/retry/` -- resets the failed task + all cascade-blocked descendants to `pending`
- The task processor picks them up on the next polling cycle
- Frontend provides retry buttons on both the `/tasks` dashboard and the video detail page

## Task Documents

| # | Task | Document | Dependencies |
|---|------|----------|-------------|
| 1 | Audio extraction + ASR transcript | [task_extract_audio_and_transcript.md](task_extract_audio_and_transcript.md) | None |
| 2 | HLS adaptive streaming | [task_hls_streaming.md](task_hls_streaming.md) | None |
| 3 | SSIM slide detection | [task_ssim_move_detection.md](task_ssim_move_detection.md) | None |
| 4 | Thumbnail generation | [task_generate_thumbnails.md](task_generate_thumbnails.md) | T3 |
| 5 | Hybrid video chunking | [task_hybrid_chunking.md](task_hybrid_chunking.md) | T4, T1 (via DB) |
| 6 | Knowledge point extraction | [task_fine_grained_knowledge.md](task_fine_grained_knowledge.md) | T5 |
| 7 | Knowledge embedding | [task_embed_knowledge.md](task_embed_knowledge.md) | T6 |
| 8 | Coarse-grained summary | [task_coarse_grained_summary.md](task_coarse_grained_summary.md) | T7 |
| 9 | Knowledge mindmap | [task_generate_mindmap.md](task_generate_mindmap.md) | T8 |

## Common Conventions

- All task functions accept `Dict[str, Any]` as input and return `Dict[str, Any]`
- Every output must include `"video_id"` for downstream task chaining
- Tasks raise exceptions on failure; the processor catches them and records error details
- Source code: `server/app/api/tasks.py`
- Task registry: `TASK_REGISTRY` dict mapping function names to callables
