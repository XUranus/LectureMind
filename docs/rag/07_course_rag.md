# Course-Level RAG — Cross-Video Search

## Overview

The course-level RAG system extends the single-video agent to search across **all videos in a course (episode)**. This enables questions that span multiple lectures, such as comparing concepts, tracking topic evolution, or finding which lecture covers a specific topic.

## Architecture

```
Student Question
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  CourseAgentRunner                                       │
│                                                          │
│  System Prompt: "You are an assistant for course         │
│  '{title}' containing {N} lecture videos..."             │
│                                                          │
│  ReAct Loop (max 5 iterations):                          │
│                                                          │
│    LLM decides tool call                                 │
│         │                                                │
│         ▼                                                │
│    ┌────────────────────────────────────────┐            │
│    │  Execute tool across ALL videos:       │            │
│    │                                        │            │
│    │    for vid in video_ids:               │            │
│    │      result = execute_tool(vid, ...)   │            │
│    │      if relevant: collect result       │            │
│    │                                        │            │
│    │    merge results with [Video xxx...] prefix │       │
│    └────────────────────────────────────────┘            │
│         │                                                │
│         ▼                                                │
│    Feed merged results back to LLM                       │
│         │                                                │
│    Repeat or produce final answer                        │
└─────────────────────────────────────────────────────────┘
```

## Class: `CourseAgentRunner`

Defined inline in `views.py` alongside the course agent endpoint.

### Constructor

```python
runner = CourseAgentRunner(
    video_ids=["uuid1", "uuid2", "uuid3"],
    episode_title="Introduction to Machine Learning",
    chat_history=[...]
)
```

### Key Difference from `AgentRunner`

The single-video `AgentRunner` calls `execute_tool(self.video_id, tool_name, args)` once per tool call.

The `CourseAgentRunner` calls `execute_tool(vid, tool_name, args)` **for every video** in the course and merges the results:

```python
combined_results = []
for vid in self.video_ids:
    result = execute_tool(vid, tool_name, args)
    if result and "not found" not in result.lower():
        combined_results.append(f"[Video {vid[:8]}...] {result[:500]}")

merged = "\n\n---\n\n".join(combined_results)
```

### Result Filtering

Empty or "not found" results are excluded from the merge. This prevents the LLM from being overwhelmed by irrelevant "No results" messages when a topic only appears in some lectures.

### Result Truncation

Each per-video result is truncated to 500 characters, and the total merged result is truncated to 2000 characters. This keeps the context window manageable even for courses with many videos.

## System Prompt (Course Mode)

```
You are an expert teaching assistant for a course titled "{title}"
containing {N} lecture videos.
You help students understand content across ALL lectures in this course.

## Your Process:
1. **Analyze** the student's question
2. **Search** across lectures using the available tools — each call
   searches all lectures in the course
3. **Synthesize** findings into a comprehensive answer, noting which
   lecture each piece of information comes from

## Rules:
- ALWAYS use at least one tool before answering
- For cross-lecture comparisons, call search_knowledge multiple times
- Mention which lecture/section each piece of info is from when citing
- Use markdown formatting
```

## API Endpoint

```
POST /api/episodes/<uuid>/agent/stream/
```

**Request body:** Same as single-video chat:
```json
{
  "message": "Compare how neural networks are introduced across all lectures",
  "session_id": "uuid"
}
```

**Response:** Same SSE event stream as the single-video agent (thinking, tool_call, tool_result, token, citations, done, complete).

## Session Storage

Course chat sessions are stored as regular `ChatSession` records, linked to the **first video** in the course. The session title is prefixed with `[Course]`:

```python
session = ChatSession.objects.create(
    video=first_video,
    title=f"[Course] {message[:80]}"
)
```

## Frontend: CourseChatbot Component

The `CourseChatbot.tsx` component is a dedicated chat UI for course-level queries:

- Located at `/courses/:courseId` (CourseDetailPage)
- Left panel: course info + scrollable video list
- Right panel: full-height chatbot
- Purple gradient header indicating "Course Agent" mode
- Same SSE parsing and tool step display as `LectureChatbot`
- Hits `POST /api/episodes/<courseId>/agent/stream/` instead of the video endpoint

## Limitations

1. **Latency:** Cross-video search is N times slower than single-video (serial execution per video)
2. **Context window:** With many videos and long results, the merged context may be aggressively truncated
3. **Citation linking:** Citations from course-level chat don't link to a specific video's player (the chat UI shows timestamps but can't navigate to the right video)
4. **Tool schema:** Same 5 tools are used as single-video mode; no course-specific tools (e.g., "compare across videos" is emergent from the LLM's reasoning, not a dedicated tool)
