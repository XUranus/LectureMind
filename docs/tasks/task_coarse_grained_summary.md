# Task: task_coarse_grained_summary

## Overview

Aggregates all sections and their fine-grained knowledge points into a single video-level summary using the LLM. Produces a high-level overview, key topics, learning objectives, prerequisites, and difficulty assessment.

**Position in DAG:** Task 8 (depends on T7: task_embed_knowledge)

## Input

```json
{
  "video_id": "uuid-string",
  "embedded_knowledge_points": 24,
  "embedded_sections": 7
}
```

## Output

```json
{
  "video_id": "uuid-string",
  "summary_created": true
}
```

## Processing Steps

### Step 1: Data Gathering

Queries the database for:
- `Video` record (for title)
- All `VideoSection` records (ordered by section order)
- All `KnowledgePoint` records (with section FK for grouping)

### Step 2: Prompt Construction

Builds a structured text block listing each section with its knowledge points:

```
Section 1: Introduction to ML (00:00-05:30)
  - Supervised Learning: Classification and regression approaches...
  - Feature Engineering: Techniques for transforming raw data...

Section 2: Neural Networks (05:30-12:00)
  - Perceptron Model: The simplest neural network unit...
```

This text is truncated at 6000 characters if a lecture has very many sections/knowledge points.

### Step 3: LLM Call

Uses `COARSE_SUMMARY_PROMPT` template with:
- Temperature: 0.3
- Max tokens: 2048
- Model: default (configurable via `LLM_MODEL`)

### Step 4: Persistence

The parsed JSON response is saved as a `KnowledgeSummary` record (1:1 with Video, uses `update_or_create`).

## LLM Output Schema

```json
{
  "overview": "This lecture provides a comprehensive introduction to machine learning...",
  "key_topics": ["Supervised Learning", "Neural Networks", "Backpropagation"],
  "learning_objectives": [
    "Understand the difference between supervised and unsupervised learning",
    "Explain how backpropagation works in neural networks"
  ],
  "prerequisites": ["Linear algebra basics", "Calculus fundamentals"],
  "difficulty_level": "intermediate"
}
```

## Fallback Behavior

If the LLM call fails, a fallback summary is created:
```json
{
  "overview": "Summary generation failed for video <title>.",
  "key_topics": [],
  "learning_objectives": [],
  "prerequisites": [],
  "difficulty_level": "unknown"
}
```

The task still succeeds (returns `summary_created: true`) so downstream tasks are not blocked.

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `KnowledgeSummary` | Create or Update (1:1 with Video) |

## Frontend Display

The summary is displayed in the **Summary** tab of the video analysis page:
- Overview as a paragraph
- Key topics as blue tags
- Learning objectives as a bullet list
- Prerequisites as orange tags
- Difficulty as a colored badge (green/orange/red)
