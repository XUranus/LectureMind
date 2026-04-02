Here is a page of slides for a presentation on the system architecture of our video processing and AI integration project.


Here is the System Architecture Overview:

```
┌─────────────────────────────────────────────────────┐
│              Frontend (React + TypeScript)          │
│   Upload │ Player │ Transcript │ Chat │ Mindmap    │
└─────────────────────┬───────────────────────────────┘
                      │ REST API + SSE
┌─────────────────────┴───────────────────────────────┐
│              Backend (Django + DRF)                 │
│  ┌─────────────────────────────────────────────┐    │
│  │     Async Task Pipeline (DAG Executor)      │    │
│  │                                             │    │
│  │  ASR │ HLS │ SSIM │ Chunking │ Knowledge   │    │
│  └─────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────┐    │
│  │     AI Services: LLM │ Embeddings │ RAG     │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```


Speaker Notes:
Our project has a classic B-S architecture. The frontend is built with React and TypeScript, providing interfaces for video upload, playback, transcript viewing, chatbot interaction, and mindmap visualization. The backend uses Django with Django REST Framework. The core intelligence lies in our async task pipeline, which processes videos through a directed acyclic graph of tasks. This allows parallel execution where possible and proper dependency management.


Generate a System Architecture Overview image according to the information.


















Here is a page of slides for a presentation on  Video Processing Pipeline (Task DAG) of our video processing and AI integration project.

Here is the pipline description:
```
Upload Video
     │
     ├──→ T1: ASR Transcription ─────────────┐
     │    (Audio extract → DashScope Qwen3)   │  Parallel
     ├──→ T2: HLS Encoding ──────────────────┤  (no deps)
     │    (Multi-resolution streaming)        │
     └──→ T3: SSIM Slide Detection ──────────┘
          (Frame change detection)
               │
               └──→ T4: Thumbnail Generation
                    (Extract frames at transitions)
                         │
                         └──→ T5: Hybrid Chunking
                              (Slide + Silence + Semantic)
                                   │
                                   └──→ T6: Fine-Grained Knowledge
                                        (LLM extraction per section)
                                             │
                                             └──→ T7: Embed Knowledge
                                                  (Vector DB storage)
                                                       │
                                                       └──→ T8: Coarse Summary
                                                            (Lecture-level aggregation)
                                                                 │
                                                                 └──→ T9: Mindmap
                                                                      (Concept hierarchy)
```

Here is the Speaker Notes:

This is the heart of our system - a 9-task directed acyclic graph. Tasks 1, 2, and 3 run in parallel since they have no dependencies. T1 extracts audio and transcribes using Alibaba's DashScope Qwen3-ASR. T2 creates HLS streaming files for adaptive playback. T3 detects slide transitions using SSIM analysis. Once T3 completes, T4 generates thumbnails at detected slide changes. T5 then performs hybrid chunking, combining slide transitions with silence detection to create meaningful sections. The remaining tasks T6 through T9 form a sequential chain for AI-powered knowledge extraction, embedding, summarization, and mindmap generation.


Draw the DAG pipeline image according to the description above.














Here is a pipeline of our Quick RAG system:

```
User Question
     │
     ▼
Embed question (all-MiniLM-L6-v2)
     │
     ▼
Vector search (top-6, cosine similarity)
     │
     ▼
Filter by relevance ≥ 0.2
     │
     ▼
Build context prompt + Lecture Overview
     │
     ▼
Stream LLM response (qwen3-max, temp=0.5)
     │
     ▼
Return answer + citations
```

In Quick RAG, we embed the question, search the vector store, filter low-relevance results, and build a context-augmented prompt. We also inject the lecture summary as background context. The LLM then generates a grounded answer with citations. The entire process takes 2-5 seconds with streaming.

Draw the pipeline image according to the description above.








Draw this graph:
```
User Question
     │
     ▼
┌─────────────────────────────────────┐
│ ReAct Loop (max 5 iterations):      │
│                                     │
│  1. LLM analyzes + decides tool     │
│  2. Execute tool                    │
│  3. Feed result back to LLM         │
│  4. Decide: another tool OR answer  │
└─────────────────────────────────────┘
     │
     ▼
Stream answer + tool steps + citations
```



