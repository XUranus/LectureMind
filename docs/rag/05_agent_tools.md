# Agent Tools — Definitions and Execution

## Overview

The agent tools (`agent_tools.py`) define the capabilities available to the ReAct agent. Each tool is an OpenAI function-calling schema paired with a Python execution function that queries Django models or the ChromaDB vector store and returns formatted text for the LLM to reason over.

## Tool Registry

### 1. `search_knowledge`

**Purpose:** Semantic search over embedded knowledge points and section transcripts.

**When to use:** Student asks about a specific concept, term, or topic.

**Schema:**
```json
{
  "name": "search_knowledge",
  "parameters": {
    "query": {"type": "string", "description": "concept/term/question to look up"},
    "top_k": {"type": "integer", "default": 5}
  },
  "required": ["query"]
}
```

**Execution:** Calls `VectorStore.query(query_text, video_id, top_k)` and formats results as:
```
[Result 1] (knowledge_point) "Gradient Descent" [02:00 - 03:00] (relevance: 0.85)
Gradient Descent: An optimization algorithm used to minimize the loss function
by iteratively adjusting parameters in the direction of steepest descent...

[Result 2] (section_transcript) "Optimization Techniques" [01:30 - 04:00] (relevance: 0.72)
So today we're going to talk about how we optimize neural networks...
```

**Data sources:** ChromaDB vector store (knowledge points + section transcripts)

---

### 2. `get_section_details`

**Purpose:** Retrieve the full transcript and all knowledge points for a specific lecture section.

**When to use:** Deep dive into a particular segment; follow-up on a search result.

**Schema:**
```json
{
  "name": "get_section_details",
  "parameters": {
    "section_order": {"type": "integer", "description": "section index (0-based)"}
  },
  "required": ["section_order"]
}
```

**Execution:** Queries `VideoSection` + related `KnowledgePoint` records. Returns:
```markdown
## Section 3: Optimization Techniques
Time: 05:30 - 12:00

### Transcript:
So in this section we're going to cover the main optimization algorithms...

### Knowledge Points:
- **Gradient Descent** (importance: 0.9)
  The standard optimization algorithm for neural networks...
  Key terms: gradient, loss function, learning rate

- **Stochastic Gradient Descent** (importance: 0.8)
  A variant that uses random mini-batches...
  Key terms: mini-batch, stochastic, variance
```

**Data sources:** Django ORM (`VideoSection`, `KnowledgePoint`)

---

### 3. `get_lecture_summary`

**Purpose:** Get the high-level overview of the entire lecture.

**When to use:** General questions ("What is this lecture about?"), prerequisite checks, difficulty assessment.

**Schema:**
```json
{
  "name": "get_lecture_summary",
  "parameters": {},
  "required": []
}
```

**Execution:** Queries `KnowledgeSummary` record. Returns:
```markdown
# Lecture Summary: Introduction to Machine Learning

**Overview:** This lecture provides a comprehensive introduction to...

**Key Topics:** Supervised Learning, Neural Networks, Backpropagation

**Learning Objectives:**
- Understand the difference between supervised and unsupervised learning
- Explain how backpropagation works

**Prerequisites:** Linear algebra basics, Calculus fundamentals

**Difficulty Level:** intermediate
```

**Data sources:** Django ORM (`KnowledgeSummary`, `Video`)

---

### 4. `list_sections`

**Purpose:** List all sections/chapters with titles, time ranges, and knowledge point counts.

**When to use:** Understanding lecture structure, finding which section covers a topic.

**Schema:**
```json
{
  "name": "list_sections",
  "parameters": {},
  "required": []
}
```

**Execution:** Queries all `VideoSection` records ordered by `order`. Returns:
```markdown
# Lecture Sections

- **Section 0:** Course Introduction [00:00 - 05:30] (2 knowledge points)
- **Section 1:** Supervised Learning Basics [05:30 - 15:00] (4 knowledge points)
- **Section 2:** Neural Network Architecture [15:00 - 28:00] (5 knowledge points)
- **Section 3:** Training and Optimization [28:00 - 42:00] (3 knowledge points)
```

**Data sources:** Django ORM (`VideoSection` + count of related `KnowledgePoint`)

---

### 5. `get_transcript_at_time`

**Purpose:** Get the raw transcript text around a specific timestamp.

**When to use:** "What was said at 10:30?", verifying a specific claim, getting exact wording.

**Schema:**
```json
{
  "name": "get_transcript_at_time",
  "parameters": {
    "time_seconds": {"type": "number", "description": "timestamp in seconds"},
    "window_seconds": {"type": "number", "default": 30, "description": "context window"}
  },
  "required": ["time_seconds"]
}
```

**Execution:** Queries `TranscriptSentence` records within `[time - window/2, time + window/2]` milliseconds. Returns:
```markdown
# Transcript around 10:30 (window: 30s)

[10:15] So the key insight here is that gradient descent
[10:18] doesn't always converge to the global minimum.
[10:22] In fact, for non-convex loss functions,
[10:25] we might get stuck in local minima.
[10:30] That's why we use techniques like momentum
[10:33] and learning rate scheduling.
```

**Data sources:** Django ORM (`TranscriptSentence`)

## Tool Execution Dispatch

```python
def execute_tool(video_id: str, tool_name: str, arguments: Dict) -> str:
```

The dispatcher routes tool calls to the appropriate `_tool_*` function. All tool functions:
- Accept `video_id` + tool-specific keyword arguments
- Return a formatted **string** (not JSON) that the LLM can directly reason over
- Catch exceptions and return error messages rather than crashing the agent loop

## Error Handling

If a tool execution fails, the error is returned as a text string to the LLM:
```
Tool execution error: VideoSection matching query does not exist.
```

The LLM can then decide to try a different tool or inform the user. This design prevents tool failures from crashing the entire agent loop.
