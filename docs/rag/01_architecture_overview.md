# RAG Architecture Overview

## System Purpose

The RAG system transforms LectureMind from a passive video viewer into an interactive learning assistant. Students can ask questions in natural language and receive answers grounded in the actual lecture content, with timestamp-linked citations that allow jumping directly to the relevant video segment.

## Two Operating Modes

### Mode 1: Quick RAG (Direct Retrieval)

```
User Question
     │
     ▼
┌─────────────────────────────┐
│ 1. Embed question           │  (all-MiniLM-L6-v2, 384-dim)
│ 2. Vector search (top-6)    │  (ChromaDB, cosine similarity)
│ 3. Filter by relevance≥0.2  │
│ 4. Build context prompt     │  (system + summary + sources + question)
│ 5. Stream LLM response      │  (qwen3-max, temperature=0.5)
│ 6. Return citations         │
└─────────────────────────────┘
     │
     ▼
Streaming Answer + Citations
```

- **Latency:** 2-5 seconds to first token
- **Best for:** Factual questions with clear answers in the lecture
- **Limitation:** Can't do multi-step reasoning or combine info from different tools

### Mode 2: Agent (ReAct Multi-Step)

```
User Question
     │
     ▼
┌─────────────────────────────────────────────────┐
│ ReAct Loop (max 5 iterations):                   │
│                                                   │
│   1. LLM analyzes question + decides tool call    │
│   2. Execute tool (search, section, summary...)   │
│   3. Feed result back to LLM                      │
│   4. LLM decides: use another tool OR respond     │
│   5. Repeat until final text response              │
│   6. Stream final answer + extract citations       │
└─────────────────────────────────────────────────┘
     │
     ▼
Streaming Answer + Tool Steps + Citations
```

- **Latency:** 5-15 seconds (multiple LLM calls)
- **Best for:** Complex questions, comparisons, structural queries
- **Advantage:** Can consult multiple information sources and chain reasoning

### Mode 3: Course Agent (Cross-Video)

Same ReAct loop as Mode 2, but each tool call is executed against **every video** in the course. Results are merged across videos, enabling cross-lecture questions like "Compare how gradient descent is explained in Lecture 1 vs Lecture 3."

## Data Flow: From Upload to Query

```
Upload → ASR → SSIM → Thumbnails → Chunking → Knowledge → Embedding
                                                              │
                                                    ChromaDB (vector store)
                                                              │
                                            ┌─────────────────┤
                                            │                 │
                                    Quick RAG            Agent Mode
                                    (single query)     (tool loop)
                                            │                 │
                                            └────────┬────────┘
                                                     │
                                              LLM (qwen3-max)
                                                     │
                                              Streaming Answer
```

## Knowledge Hierarchy

The RAG system searches across two granularity levels stored in ChromaDB:

| Level | Source | Embed Text | Count (typical) |
|-------|--------|-----------|------------------|
| **Knowledge Point** | LLM-extracted from each section | `"Title: Summary (Key terms: t1, t2)"` | 15-40 per video |
| **Section Transcript** | Raw ASR transcript per section | First 2000 chars of transcript | 5-15 per video |

Additionally, the coarse-grained `KnowledgeSummary` (overview, topics, objectives) is injected directly into the RAG prompt as context — not embedded separately.

## Session Management

Chat sessions are persisted in the Django database:

```
ChatSession (1:many with ChatMessage)
├── id: UUID
├── video: FK → Video
├── title: auto-generated from first question
├── created_at, updated_at
│
└── ChatMessage
    ├── role: "user" | "assistant"
    ├── content: text (markdown)
    ├── citations: JSON list [{source_num, title, begin_time, end_time, type, relevance}]
    └── created_at
```

Both Quick RAG and Agent modes share the same session system. The session provides multi-turn context (last 6 messages are included in the LLM prompt).
