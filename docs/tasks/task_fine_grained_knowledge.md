# Task: task_fine_grained_knowledge

## Overview

Iterates over each video section produced by hybrid chunking and uses the LLM (Qwen) to extract structured knowledge points. For each section, the LLM analyzes the transcript text and produces a descriptive section title, 1-5 knowledge points (each with title, summary, key terms, and importance score).

**Position in DAG:** Task 6 (depends on T5: task_hybrid_chunking)

## Input

```json
{
  "video_id": "uuid-string",
  "section_count": 8
}
```

## Output

```json
{
  "video_id": "uuid-string",
  "knowledge_points_count": 24,
  "sections_processed": 7
}
```

## Processing Steps

### For Each Section:

1. **Skip check:** Sections with transcript text < 20 characters are skipped (likely silence-only segments).

2. **Prompt construction:** The transcript text (truncated to 3000 characters) is formatted into the `FINE_GRAINED_EXTRACTION_PROMPT` template along with the section title and time range.

3. **LLM call:** `LLMClient.chat()` with:
   - System prompt: "You are an expert educational content analyst. Respond with valid JSON only."
   - Temperature: 0.3 (consistent structured output)
   - Max tokens: 2048
   - Model: default (`qwen2.5-7b-instruct` or configured via `LLM_MODEL`)

4. **Response parsing:** The LLM response is parsed as JSON using `_parse_llm_json()` which handles:
   - Raw JSON responses
   - Markdown-fenced JSON (```json ... ```)
   - JSON embedded in prose text

5. **Section title update:** The LLM-generated `section_title` replaces the generic "Section N" title.

6. **Knowledge point creation:** Each extracted point is saved as a `KnowledgePoint` record.

### Error Isolation

If a single section fails (LLM error, JSON parse error), the task logs the error and continues to the next section. This ensures one problematic section doesn't block knowledge extraction for the entire video.

## LLM Prompt Template

```
You are an expert educational content analyst. Analyze the following lecture segment
and extract structured knowledge points.

Section: {section_title}
Time range: {time_range}

Transcript:
---
{transcript}
---

Extract the following in JSON format:
{
  "section_title": "A concise, descriptive title (5-10 words)",
  "points": [
    {
      "title": "Knowledge point title (3-8 words)",
      "summary": "2-3 sentence explanation",
      "terms": ["key term 1", "key term 2"],
      "importance": 0.0-1.0
    }
  ]
}
```

## LLM Output Schema

```json
{
  "section_title": "Introduction to Neural Network Architectures",
  "points": [
    {
      "title": "Feedforward Network Structure",
      "summary": "A feedforward neural network consists of layers...",
      "terms": ["feedforward", "hidden layer", "activation function"],
      "importance": 0.9
    }
  ]
}
```

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `KnowledgePoint` | Delete all existing for video + create new |
| `VideoSection` | Update `title` field with LLM-generated title |

## LLM Call Logging

Every LLM call is logged to `logs/llm_calls/<timestamp>_chat_messages.json` with full request/response details for debugging.

## Approximate Duration

Depends on section count and LLM response time:
- ~3-8 seconds per section (API latency)
- 10 sections: ~30-80 seconds
- 20 sections: ~60-160 seconds
