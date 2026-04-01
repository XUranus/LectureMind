# Frontend Integration — Chat UI Components

## Overview

The RAG system is exposed to users through two React components: `LectureChatbot` (single video, with Agent/Quick toggle) and `CourseChatbot` (course-wide). Both implement SSE streaming, markdown rendering, tool step visualization, and clickable source citations.

## Component: `LectureChatbot`

**File:** `frontend/src/components/lecture/LectureChatbot.tsx`
**Used in:** Video detail page (`/lecture/:videoId`), Chat tab

### Features

| Feature | Description |
|---------|-------------|
| **Agent/Quick toggle** | Switch between Quick RAG (direct retrieval) and Agent mode (multi-step reasoning) |
| **SSE streaming** | Token-by-token display with blinking cursor |
| **Markdown rendering** | Full GitHub Flavored Markdown via `react-markdown` + `remark-gfm` |
| **Tool step display** | Real-time tool call/result visualization during agent execution |
| **Source citations** | Clickable timestamp badges that jump the video player |
| **Abort control** | "Stop" button to cancel in-progress generation |
| **Session persistence** | Auto-creates session on first message, reuses for follow-ups |

### Mode Toggle

A `<Switch>` in the header bar toggles between modes:

- **Agent Mode** (purple theme): Hits `POST /api/videos/<id>/agent/stream/`
  - Shows `RobotOutlined` icon, "Multi-step reasoning with tools" subtitle
  - Displays live tool activity during generation (purple activity panel)
  - Tool steps are shown inline in the assistant message after generation
  
- **Quick Mode** (blue theme): Hits `POST /api/videos/<id>/chat/stream/`
  - Shows `ThunderboltOutlined` icon, "Direct RAG retrieval" subtitle
  - No tool steps — just streaming text + citations

### SSE Client Implementation

```typescript
const response = await fetch(endpoint, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: text, session_id: sessionId }),
  signal: controller.signal,  // AbortController for cancel
});

const reader = response.body?.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop() || '';
  
  let currentEvent = '';
  for (const line of lines) {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7).trim();
    } else if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      // Handle event based on currentEvent type
    }
  }
}
```

### Event Handling

| SSE Event | Frontend Action |
|-----------|----------------|
| `thinking` | Show thinking indicator (purple spinner + text) |
| `tool_call` | Add to `currentToolSteps` array, show in activity panel |
| `tool_result` | Update last tool step with result preview |
| `token` | Append to assistant message content |
| `citations` | Set citations on assistant message |
| `done` | Move `currentToolSteps` into message's `toolSteps` field |
| `complete` | Update `sessionId` + `messageId` for persistence |
| `error` | Display error in message content |

### Citation Badges (`CitationBadge`)

Each citation renders as an Ant Design `<Tag>`:

```
[BulbIcon] [ClockIcon] 02:00  [Source 1]
```

- **Blue** for `knowledge_point` type, **cyan** for `section_transcript`
- **Tooltip** shows full title and time range
- **Click** calls `handleTimeClick(citation.begin_time)` which propagates up to `jumpVideoTime()` in the parent `LectureVideoAnalysis`, seeking the video player

### Tool Step Display (`ToolStepDisplay`)

Each tool step shows:
```
[SearchIcon] Searching knowledge (query: "gradient descent")
  └── [Collapse] Show result → <pre>truncated result text</pre>
```

- Tool name mapped to friendly label via `toolLabels` dict
- Tool icon via `toolIcons` dict
- Arguments shown inline
- Result in a collapsible `<Collapse>` panel (prevents UI clutter)

### Message Layout

```
┌──────────────────────────────────────────────┐
│                  Chat Area                    │
│                                               │
│  ┌──── User Message ────────────────────┐    │
│  │  "What is gradient descent?"     [R] │    │
│  └──────────────────────────────────────┘    │
│                                               │
│  ┌──── Assistant Message ───────────────┐    │
│  │  ┌─ Tool Steps (if agent mode) ────┐ │    │
│  │  │  🔍 Searching knowledge (...)    │ │    │
│  │  │  📄 Reading section (...)        │ │    │
│  │  └─────────────────────────────────┘ │    │
│  │                                       │    │
│  │  Gradient descent is an optimization  │    │
│  │  algorithm that...                    │    │
│  │                                       │    │
│  │  ┌─ Sources ───────────────────────┐ │    │
│  │  │ [💡 02:00 [Src 1]] [📄 05:30 [Src 2]] │    │
│  │  └─────────────────────────────────┘ │    │
│  └──────────────────────────────────────┘    │
│                                               │
│  ┌──── Live Activity (during generation) ─┐  │
│  │  ⏳ Analyzing question (step 2)...      │  │
│  │  🔍 Searching knowledge (query: "...")  │  │
│  └────────────────────────────────────────┘  │
│                                               │
├──────────────────────────────────────────────┤
│  [Input: Ask about the lecture...  ] [Send]  │
└──────────────────────────────────────────────┘
```

## Component: `CourseChatbot`

**File:** `frontend/src/components/lecture/CourseChatbot.tsx`
**Used in:** Course detail page (`/courses/:courseId`)

### Differences from `LectureChatbot`

| Aspect | LectureChatbot | CourseChatbot |
|--------|---------------|---------------|
| Endpoint | `/api/videos/<id>/agent/stream/` | `/api/episodes/<id>/agent/stream/` |
| Mode toggle | Agent / Quick | Agent only (always multi-step) |
| Theme | Blue/purple | Purple gradient header |
| Scope text | — | "Searches across all lectures in '{title}'" |
| Citation clicks | Jump video player | Display only (no video player) |

### Layout in CourseDetailPage

```
┌───────────────────────────────────────────────────┐
│  [← Back to Courses]                               │
│  Course Title                                       │
│  Description text...                                │
│  [📹 N videos]  Created: 2026-03-15                │
├──────────────────┬────────────────────────────────┤
│  Lectures        │  Course Agent Chatbot           │
│                  │                                  │
│  1. [thumb] L1   │  [🤖 Course Agent]              │
│  2. [thumb] L2   │  [searches all lectures in...] │
│  3. [thumb] L3   │                                  │
│  ...             │  (same chat UI as LectureChatbot│
│                  │   but agent-only, purple theme) │
│                  │                                  │
└──────────────────┴────────────────────────────────┘
```

## TypeScript Types

### `ChatMessageData`
```typescript
interface ChatMessageData {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
  toolSteps?: AgentToolStep[];
  created_at?: string;
}
```

### `Citation`
```typescript
interface Citation {
  source_num: number;
  title: string;
  begin_time: number;  // seconds
  end_time: number;    // seconds
  type: string;        // "knowledge_point" | "section_transcript" | "section"
  relevance: number;   // 0.0 - 1.0
}
```

### `AgentToolStep`
```typescript
interface AgentToolStep {
  tool: string;             // "search_knowledge" | "get_section_details" | ...
  args: Record<string, any>;
  result?: string;           // truncated result preview
}
```

### SSE Event Types
```typescript
type AgentEventType =
  | 'thinking'    // agent reasoning
  | 'tool_call'   // tool invocation
  | 'tool_result' // tool output
  | 'token'       // answer text chunk
  | 'citations'   // source citations
  | 'done'        // tool steps summary
  | 'complete'    // persistence IDs
  | 'error';      // error occurred
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `react-markdown` | Markdown rendering in chat messages |
| `remark-gfm` | GitHub Flavored Markdown (tables, strikethrough, etc.) |
| `antd` | UI components (Button, Tag, Tooltip, Collapse, Switch, Spin) |
| `@ant-design/icons` | Icons for tools, status indicators |
