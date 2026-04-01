# Chat API — REST Endpoints and SSE Streaming Protocol

## Overview

The chat system exposes REST endpoints for session management and Server-Sent Events (SSE) endpoints for real-time streaming responses. Both Quick RAG and Agent modes share the same session persistence layer.

## Endpoints

### Session Management

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/api/videos/<uuid>/chat/sessions/` | List all sessions for a video |
| POST | `/api/videos/<uuid>/chat/sessions/` | Create a new session |
| GET | `/api/chat/sessions/<uuid>/` | Get session with all messages |
| DELETE | `/api/chat/sessions/<uuid>/` | Delete a session |
| GET | `/api/chat/sessions/<uuid>/messages/` | List messages in a session |

### Chat (Quick RAG)

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/videos/<uuid>/chat/stream/` | SSE streaming RAG chat |
| POST | `/api/videos/<uuid>/chat/ask/` | Non-streaming RAG chat |

### Chat (Agent)

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/api/videos/<uuid>/agent/stream/` | SSE streaming agent chat (single video) |
| POST | `/api/episodes/<uuid>/agent/stream/` | SSE streaming agent chat (course-wide) |

## Request Format

All chat endpoints accept the same request body:

```json
{
  "message": "What is gradient descent?",
  "session_id": "uuid"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `message` | Yes | The student's question (trimmed, must be non-empty) |
| `session_id` | No | UUID of an existing session. If omitted, a new session is created with the question (truncated to 80 chars) as the title. |

## SSE Streaming Protocol

All streaming endpoints return `Content-Type: text/event-stream` with `Cache-Control: no-cache` and `X-Accel-Buffering: no` (for nginx compatibility).

### Quick RAG Events (`/chat/stream/`)

```
event: token
data: {"token": "Gradient"}

event: token
data: {"token": " descent"}

event: token
data: {"token": " is an optimization"}

event: citations
data: {"citations": [{"source_num": 1, "title": "...", "begin_time": 120.5, ...}]}

event: done
data: {"message_id": "uuid", "session_id": "uuid"}
```

| Event | Payload | Description |
|-------|---------|-------------|
| `token` | `{"token": "..."}` | Incremental text chunk from the LLM |
| `citations` | `{"citations": [...]}` | Source citations after answer generation |
| `done` | `{"message_id": "...", "session_id": "..."}` | Completion signal with persisted IDs |
| `error` | `{"error": "...", "message_id": "..."}` | Error (still saves an error message) |

### Agent Events (`/agent/stream/` and `/episodes/<id>/agent/stream/`)

All Quick RAG events plus:

| Event | Payload | Description |
|-------|---------|-------------|
| `thinking` | `{"thought": "Analyzing question (step 1)..."}` | Agent reasoning step |
| `tool_call` | `{"tool": "search_knowledge", "args": {"query": "..."}}` | Agent invokes a tool |
| `tool_result` | `{"tool": "...", "result": "preview..."}` | Tool execution result (300-char preview) |
| `done` | `{"tool_steps": [...]}` | Includes full tool step history |
| `complete` | `{"message_id": "...", "session_id": "..."}` | Final persistence signal |

### Event Sequence Diagram

```
Quick RAG:
  token → token → ... → token → citations → done

Agent:
  thinking → tool_call → tool_result →
  thinking → tool_call → tool_result →
  thinking → token → ... → token →
  citations → done → complete
```

## Session Lifecycle

### Auto-Creation

If `session_id` is omitted from the request, a new `ChatSession` is created:
```python
title = message[:80] + ("..." if len(message) > 80 else "")
session = ChatSession.objects.create(video=video, title=title)
```

### Message Persistence

Every exchange is persisted to the database:

1. **Before generation:** The user message is saved as a `ChatMessage` with `role="user"`
2. **After generation:** The assistant response is saved with `role="assistant"`, including the full `citations` JSON array
3. **On error:** An error message is still saved so the user can see what went wrong

### Multi-Turn Context

Chat history is built from the session's message records:
```python
history = ChatMessage.objects.filter(session=session).order_by('created_at').values('role', 'content')
# Last 6 messages are included in the LLM prompt (excluding the just-saved user message)
```

## Non-Streaming Fallback (`/chat/ask/`)

Returns a single JSON response:

```json
{
  "answer": "Gradient descent is an optimization algorithm...",
  "citations": [{"source_num": 1, "title": "...", "begin_time": 120.5, ...}],
  "session_id": "uuid",
  "message_id": "uuid"
}
```

Useful for programmatic access or testing, but the frontend always uses the streaming endpoint.

## HTTP Response Headers

```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

The `X-Accel-Buffering: no` header prevents nginx from buffering the SSE stream, ensuring tokens are delivered in real-time.
