# RAG System Design — LectureMind

This directory documents the Retrieval-Augmented Generation (RAG) system that powers lecture Q&A in LectureMind. The system enables students to ask natural language questions about any processed lecture video and receive grounded, citation-backed answers.

## Document Index

| Document | Description |
|----------|-------------|
| [01_architecture_overview.md](01_architecture_overview.md) | High-level architecture, two operating modes, data flow |
| [02_knowledge_store.md](02_knowledge_store.md) | Vector store design, embedding pipeline, ChromaDB configuration |
| [03_rag_engine.md](03_rag_engine.md) | Core RAG pipeline — retrieval, context assembly, prompt engineering |
| [04_agent_system.md](04_agent_system.md) | ReAct agent with tool orchestration for multi-step reasoning |
| [05_agent_tools.md](05_agent_tools.md) | Tool definitions, schemas, and execution logic |
| [06_chat_api.md](06_chat_api.md) | REST API endpoints, SSE streaming protocol, session management |
| [07_course_rag.md](07_course_rag.md) | Cross-video course-level RAG with multi-video search |
| [08_frontend_integration.md](08_frontend_integration.md) | Chat UI components, SSE client, citation rendering |

## Quick Reference

### Two Operating Modes

| Mode | Endpoint | Scope | Reasoning |
|------|----------|-------|-----------|
| **Quick (RAG)** | `POST /api/videos/<id>/chat/stream/` | Single video | Single retrieval + generation |
| **Agent** | `POST /api/videos/<id>/agent/stream/` | Single video | Multi-step tool calls |
| **Course Agent** | `POST /api/episodes/<id>/agent/stream/` | All videos in course | Cross-video multi-step |

### System Components

```
┌──────────────────────────────────────────────────────────────┐
│                        Frontend                               │
│  LectureChatbot.tsx (Agent/Quick toggle)                      │
│  CourseChatbot.tsx (course-scoped)                            │
│       │ SSE (text/event-stream)                               │
└───────┼──────────────────────────────────────────────────────┘
        │
┌───────┼──────────────────────────────────────────────────────┐
│       ▼ Django Views (SSE endpoints)                          │
│  chat_stream_view        → RAGEngine.ask_stream()             │
│  agent_chat_stream_view  → AgentRunner.run_stream()           │
│  course_agent_stream_view→ CourseAgentRunner.run_stream()     │
│       │                                                       │
│  ┌────┴──────────────────────────────────────────────────┐   │
│  │  RAGEngine           │  AgentRunner                    │   │
│  │  (single retrieval)  │  (ReAct loop, 5 tools)         │   │
│  │       │              │       │                         │   │
│  │  VectorStore.query() │  execute_tool()                 │   │
│  │       │              │    ├─ search_knowledge          │   │
│  │  LLMClient.stream()  │    ├─ get_section_details       │   │
│  │                      │    ├─ get_lecture_summary        │   │
│  │                      │    ├─ list_sections              │   │
│  │                      │    └─ get_transcript_at_time     │   │
│  └───────────────────────────────────────────────────────┘   │
│       │                        │                              │
│  ┌────┴────────────────────────┴─────────────────────────┐   │
│  │  ChromaDB (vector store)  │  Django ORM (models)       │   │
│  │  all-MiniLM-L6-v2        │  VideoSection, KnowledgePoint│  │
│  │  cosine similarity       │  KnowledgeSummary, Transcript│  │
│  └───────────────────────────────────────────────────────┘   │
│       │                                                       │
│  ┌────┴──────────────────────────────────────────────────┐   │
│  │  LLM (qwen3-max via DashScope OpenAI-compatible API)   │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```
