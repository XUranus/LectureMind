# Task: task_slides_ocr

## Overview

Extracts text content from slide thumbnail images using the **Qwen2.5-VL-72B-Instruct** vision-language model via DashScope API. Each slide frame is sent to the VL model as a base64-encoded image, and the extracted text is stored as a `SlideOCR` record linked to the corresponding `Thumbnail`.

The OCR text is later embedded into the ChromaDB vector store (by `task_embed_knowledge`) as a `slide_ocr` content type, making slide text searchable through RAG queries.

**Position in DAG:** Task 4b (depends on T4: task_generate_thumbnails)

## Input

Receives the output of `task_generate_thumbnails` (passed via task chain):

```json
{
  "video_id": "uuid-string",
  "file": "videos/lecture1.mp4",
  "changes": [10.22, 34.56, 78.90],
  "thumbnail_count": 15
}
```

## Output

```json
{
  "video_id": "uuid-string",
  "ocr_count": 12,
  "skipped": 3
}
```

- `ocr_count`: Number of slides that had text successfully extracted
- `skipped`: Number of slides skipped (no image file, blank slides, or VL API errors)

## Processing Steps

### Step 1: Load Thumbnails

Queries all `Thumbnail` records for the video, ordered by `time_second`.

### Step 2: Encode Images

For each thumbnail, reads the image file from disk and encodes it as a base64 data URI:

```
data:image/jpeg;base64,<base64-encoded-data>
```

This is required because the DashScope VL API is a remote service that cannot access local file paths.

### Step 3: VL Model OCR

Sends each image to the **Qwen2.5-VL-72B-Instruct** model via the `LLMClient.chat_vl()` method with a carefully crafted prompt that instructs the model to:

- Extract ALL visible text (titles, bullets, equations, code, tables, captions)
- Preserve hierarchical structure using markdown formatting
- Use LaTeX notation for mathematical equations
- Use markdown code blocks for code snippets
- Respond with `[NO TEXT CONTENT]` for blank/decorative slides

**Model parameters:**
- Temperature: 0.1 (deterministic OCR)
- Max tokens: 2048
- System prompt: Expert OCR system specialized in lecture slides

### Step 4: Save OCR Records

For each successfully extracted text, creates a `SlideOCR` record:

```python
SlideOCR.objects.create(
    thumbnail=thumb,
    video_id=video_id,
    ocr_text=ocr_text,
    time_second=thumb.time_second,
)
```

Slides with `[NO TEXT CONTENT]` or empty responses are skipped.

### Step 5: Idempotent Re-run

Existing `SlideOCR` records for the video are deleted before processing, allowing safe task retry.

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `SlideOCR` | Delete all existing + create new records |

## Data Model: SlideOCR

```python
class SlideOCR(models.Model):
    id = models.UUIDField(primary_key=True)
    thumbnail = models.OneToOneField(Thumbnail)  # 1:1 with thumbnail
    video = models.ForeignKey(Video)              # denormalized FK
    ocr_text = models.TextField()                 # extracted text content
    time_second = models.FloatField()             # slide timestamp
    created_at = models.DateTimeField()
```

## API Endpoint

```
GET /api/videos/<uuid:video_id>/slide-ocr/
```

Returns all OCR results for a video, ordered by time:

```json
[
  {
    "id": "uuid",
    "thumbnail": "uuid",
    "video": "uuid",
    "ocr_text": "# Introduction to Neural Networks\n\n- Perceptron model\n- Activation functions\n- ...",
    "time_second": 10.22,
    "thumbnail_url": "/media/thumbnails/abc123.jpg",
    "created_at": "2025-01-15T10:30:00Z"
  }
]
```

## RAG Integration

In `task_embed_knowledge` (T7), slide OCR texts are embedded into ChromaDB with:

- **ID format:** `slide-ocr-<uuid>`
- **Type metadata:** `"slide_ocr"`
- **Section association:** Each OCR record is matched to its containing section by time overlap
- **Text:** OCR text content (truncated to 2000 chars for embedding)

This means RAG queries can retrieve relevant slide text alongside transcript and knowledge point content.

## Error Handling

- Individual slide OCR failures are logged and skipped (the task continues with remaining slides)
- If no thumbnails exist for the video, the task succeeds with `ocr_count: 0`
- Missing image files on disk are skipped with a warning
- VL API errors are caught per-slide and the slide is skipped

## External Dependencies

- **DashScope API** (Qwen2.5-VL-72B-Instruct model via OpenAI-compatible endpoint)
- **DASHSCOPE_API_KEY** environment variable must be set

## Performance Notes

- Each slide requires one VL API call (~2-5 seconds per slide depending on image complexity)
- A lecture with 30 slides takes approximately 1-2.5 minutes
- Images are encoded as base64 in memory; thumbnail files are typically small (~50-200KB at 200px width)
- The VL model runs remotely on DashScope infrastructure, so no local GPU is needed
