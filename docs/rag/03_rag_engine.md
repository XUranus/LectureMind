# RAG Engine — Core Retrieval-Augmented Generation

## Overview

The `RAGEngine` class (`rag_engine.py`) implements the core Quick RAG pipeline: retrieve relevant knowledge from the vector store, assemble a context-augmented prompt, and generate a grounded answer using the LLM.

## Class: `RAGEngine`

### Constructor

```python
engine = RAGEngine(video_id="uuid-str", top_k=6)
```

- `video_id`: Scopes all retrieval to a single video
- `top_k`: Maximum number of vector search results (default 6)

### Method: `ask(question, chat_history=None)`

Non-streaming. Returns `(answer_text, citations_list)`.

### Method: `ask_stream(question, chat_history=None)`

Generator yielding `(token, None)` for each text chunk, then `("", citations_list)` as the final signal.

## Pipeline Steps

### Step 1: Retrieve Context (`_retrieve_context`)

```python
citations, sources_text = self._retrieve_context(query)
```

1. Embeds the question using `all-MiniLM-L6-v2`
2. Queries ChromaDB with `video_id` filter, top-6 results
3. Filters results with `relevance < 0.2` (too dissimilar)
4. Formats each result as a numbered source block:

```
[Source 1] (knowledge_point) "Gradient Descent" [02:00 - 03:00] (relevance: 0.85)
Gradient descent is an optimization algorithm used to minimize the loss function...
```

5. Returns both the formatted text (for LLM prompt) and structured citations (for frontend)

### Step 2: Get Summary Section (`_get_summary_section`)

If a `KnowledgeSummary` exists for the video, it's included in the prompt as background context:

```markdown
### Lecture Overview
This lecture provides a comprehensive introduction to machine learning...

**Key Topics:** Supervised Learning, Neural Networks, Backpropagation
**Difficulty:** intermediate
```

This gives the LLM a broad understanding of the lecture even if the specific retrieved sources don't cover the topic.

### Step 3: Build Messages (`_build_messages`)

Assembles the full LLM message list:

```python
messages = [
    {"role": "system", "content": RAG_SYSTEM_PROMPT},
    # ... last 6 chat history messages (if multi-turn) ...
    {"role": "user", "content": RAG_CONTEXT_TEMPLATE.format(
        video_title=...,
        summary_section=...,
        sources_section=...,
        question=...
    )}
]
```

### Step 4: Generate Response

Calls `LLMClient` with:
- Model: `qwen3-max`
- Temperature: 0.5
- Max tokens: 2048
- Streaming: yes (for `ask_stream`)

## Prompt Templates

### System Prompt (`RAG_SYSTEM_PROMPT`)

```
You are a knowledgeable teaching assistant for a video lecture.
Answer the student's question based on the lecture content provided below.

Instructions:
- Answer ONLY based on the provided context. If the context doesn't contain
  enough information, say so honestly.
- When referencing specific lecture content, cite the source using [Source N]
  notation matching the numbered sources below.
- Be concise but thorough. Use markdown formatting for clarity.
- If the question is about a specific concept, explain it as taught in this lecture.
- Maintain an educational, helpful tone.
```

### Context Template (`RAG_CONTEXT_TEMPLATE`)

```
## Lecture Context

### Video: {video_title}

{summary_section}

### Retrieved Sources:
{sources_section}

---
Student Question: {question}
```

## Citation Schema

Each citation returned to the frontend:

```json
{
  "source_num": 1,
  "title": "Gradient Descent Basics",
  "begin_time": 120.5,
  "end_time": 180.0,
  "type": "knowledge_point",
  "relevance": 0.847
}
```

The `source_num` corresponds to `[Source N]` in the LLM's response text, enabling the frontend to render clickable citation badges.

## Multi-Turn Context

For follow-up questions, the last 6 messages from the chat session are included in the prompt. This allows the LLM to understand context like "Can you explain that in more detail?" or "What about the second approach?"

The limit of 6 messages (3 turns) balances context quality with token budget.
