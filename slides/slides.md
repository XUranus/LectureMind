---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  table {
    transform: scale(0.8); /* Shrinks to 80% size */
    transform-origin: top left;
  }
  
---

<style>
    .bottom-right {
    position: absolute;
    right: 20px;
    bottom: 20px;
    width: 50%;
  }
</style>


<!-- _class: lead -->

# LectureMind: AI-Powered Lecture Video Analysis

> *COMP5575 Group Project*

 - *Speaker_A* 
 - *Speaker_B*
 - *Speaker_C*


<!--
Speaker Notes:
Good evening everyone. Today we present LectureMind, an AI-powered lecture video analysis and summarization platform.
-->

---

# What is LectureMind?

**Problem:** Students struggle to navigate and review long lecture videos

**Solution:** Multi-stage AI pipeline that transforms raw lecture videos into:
- Structured segments with slide transitions
- Transcribed text with timestamps
- Extracted knowledge points
- Searchable knowledge base
- Intelligent Q&A chatbot

<!--
Speaker Notes:
LectureMind addresses a common problem: students find it difficult to efficiently review long lecture videos. Our system automatically processes lecture videos through a AI pipeline. The output includes segmented content, transcripts, extracted knowledge points, and a chatbot that can answer questions about the lecture content. This transforms passive video watching into an interactive learning experience.
-->

---
# Demo Video

TODO::

---

# System Architecture Overview

![](./assets/architecture.png)

<!--
Speaker Notes:
Our project has a classic B-S architecture. The frontend is built with React and TypeScript, providing interfaces for video upload, playback, transcript viewing, chatbot interaction, and mindmap visualization. The backend uses Django with Django REST Framework. The core intelligence lies in our async task pipeline, which processes videos through a directed acyclic graph of tasks. This allows parallel execution where possible and proper dependency management.
-->

---

# Video Processing Pipeline (Task DAG)

![](./assets/dag.png)

<!--
Speaker Notes:
This is the heart of our system - a 9-task directed acyclic graph. 
Tasks 1, 2, and 3 run in parallel since they have no dependencies. 
T1 extracts audio and transcribes using Alibaba's DashScope Qwen3-ASR. 
T2 creates HLS streaming files for adaptive playback. 
T3 detects slide transitions using SSIM analysis. 
Once T3 completes, T4 generates thumbnails at detected slide changes. 
T5 then performs hybrid chunking, combining slide transitions with silence detection to create meaningful sections. 
The remaining tasks T6 through T9 form a sequential chain for AI-powered knowledge extraction, embedding, summarization, and mindmap generation.
-->

---

# Algorithm 1: SSIM Slide Detection

**Purpose:** Detect slide transitions by analyzing frame-to-frame visual changes

**Structural Similarity Index (SSIM):**
- Measures perceived visual similarity between two images
- Range: 0 (completely different) to 1 (identical)
- Threshold: < 0.7 indicates a slide change

<!--
Speaker Notes:
Let me dive into our first key algorithm: SSIM-based slide detection. SSIM, or Structural Similarity Index, is a perceptual metric that measures image quality degradation. It's more aligned with human visual perception than simple pixel difference. 
-->

---

# Algorithm 1: SSIM Slide Detection

**Processing Pipeline:**
1. **Frame Sampling:** Read frames at 10 FPS (reduces 36K frames vs 1.8M at 30 FPS)
2. **Preprocessing:** Resize to 240px width, convert to grayscale
3. **SSIM Computation:** Multithreaded comparison (16 workers)
4. **Change Detection:** SSIM < threshold → record timestamp
5. **Cooldown:** Minimum 5-second interval between detections

<!--
Speaker Notes:
We sample frames at 10 FPS to balance accuracy with performance. Each frame is resized and converted to grayscale to reduce computational load. We implement multithreaded SSIM computation using 16 worker threads, which significantly speeds up processing. We also implement a 5-second cooldown to prevent false positives from animations or video transitions.
-->

---

# Algorithm 2: Hybrid Video Chunking

**Purpose:** Segment video into meaningful sections using multiple signals

**Three Signal Sources:**

1. **Slide Changes** (from SSIM detection)
   - Physical slide transitions

2. **Silence Gaps** (from ASR transcript)
   - Gaps ≥ 2.0 seconds between sentences
   - Indicates natural pause points

3. **Semantic Similarity** (optional, currently disabled)
   - Sentence-transformers analysis
   - Detects topic shifts in continuous speech

**Algorithm:**
```
Candidates = SlideChanges ∪ SilenceGaps
         │
         ▼
Filter by min_chunk_duration (≥30s)
         │
         ▼
(Optional) Semantic similarity check
         │
         ▼
Build final chunks with start/end times
```

<!--
Speaker Notes:
Hybrid chunking is where our system gets intelligent about segmentation. Instead of relying on a single signal, we combine three complementary approaches. Slide changes give us physical boundaries. Silence gaps from the ASR transcript indicate natural speaking pauses. We also implemented semantic similarity analysis using sentence-transformers, though this is currently disabled on memory-constrained systems. The algorithm merges all candidate split points, filters them by minimum duration, optionally checks semantic continuity, and produces the final section boundaries. This hybrid approach produces much more natural segments than any single method alone.
-->

---

# Hybrid Chunking Example

**Input:**
- SSIM slide changes: `[10.2, 34.5, 78.9, 120.0, 180.5]`
- ASR silence gaps: `[33.0, 77.5, 118.0, 250.0]`

**Merged Candidates:** `[10.2, 33.0, 34.5, 77.5, 78.9, 118.0, 120.0, 180.5, 250.0]`

**After Filtering** (min 30s duration):
- Remove 33.0 (too close to 34.5)
- Remove 77.5 (too close to 78.9)
- Remove 118.0 (too close to 120.0)

**Final Sections:**
```
Section 1: 0.0s - 34.5s    (Introduction)
Section 2: 34.5s - 78.9s   (Background)
Section 3: 78.9s - 120.0s  (Core Concept A)
Section 4: 120.0s - 180.5s (Core Concept B)
Section 5: 180.5s - end    (Summary)
```

<!--
Speaker Notes:
Here's a concrete example of how hybrid chunking works. We start with slide change timestamps from SSIM and silence gap midpoints from the ASR transcript. After merging and sorting, we apply the minimum duration filter - in this case, removing candidates that are too close together. The result is a set of well-spaced, meaningful sections. Each section typically corresponds to a coherent topic or concept in the lecture. These sections become the foundation for all downstream knowledge extraction.
-->

---

# Knowledge Extraction Pipeline

**After chunking, each section undergoes AI analysis:**

```
For each VideoSection:
    │
    ├──→ Extract transcript text (from ASR)
    │
    ├──→ Find representative thumbnail
    │
    ├──→ Call LLM (Qwen2.5-7b-instruct)
    │    Prompt: "Extract knowledge points from this lecture segment"
    │
    ├──→ Parse JSON response:
    │    {
    │      "section_title": "Gradient Descent Basics",
    │      "points": [
    │        {
    │          "title": "Learning Rate",
    │          "summary": "The learning rate controls step size...",
    │          "terms": ["learning rate", "gradient", "convergence"],
    │          "importance": 0.85
    │        }
    │      ]
    │    }
    │
    └──→ Save KnowledgePoint records
```

<!--
Speaker Notes:
Once we have our sections, we extract structured knowledge using LLMs. For each section, we send the transcript text to Qwen2.5-7b-instruct with a carefully crafted prompt. The LLM returns structured JSON with a descriptive section title and 1-5 knowledge points. Each knowledge point includes a title, summary explanation, key terminology, and an importance score. This structured output is then saved to our database. The beauty of this approach is that it transforms unstructured speech into organized, searchable knowledge.
-->

---

<!-- _class: lead -->

# Part 2: Knowledge Storage & RAG System

## Speaker 2

<!--
Speaker Notes:
Now I'll hand it over to my teammate who will discuss how we store this extracted knowledge and build our RAG system for intelligent querying.
-->

---

# Vector Database Design

**ChromaDB** - Embedded vector store for semantic search

**What Gets Embedded:**

| Content Type | Source | Embed Text Format | Count/Video |
|-------------|--------|-------------------|-------------|
| Knowledge Points | LLM extraction | `"Title: Summary (Key terms: t1, t2)"` | 15-40 |
| Section Transcripts | ASR output | First 2000 chars of transcript | 5-15 |

**Embedding Model:** `all-MiniLM-L6-v2`
- 384-dimensional vectors
- ~80 MB model size
- ~100 texts/sec encoding speed (CPU)
- Cosine similarity for retrieval

**Storage:**
```
media/chromadb/
  chroma.sqlite3          # Metadata + document text
  <uuid>/                 # HNSW index files
    data_level0.bin
    header.bin
    link_lists.bin
```

<!--
Speaker Notes:
My presentation focuses on how we store and retrieve knowledge. We use ChromaDB, an embedded vector database that doesn't require a separate server. We embed two types of content: the structured knowledge points extracted by the LLM, and raw section transcripts. The embedding model is all-MiniLM-L6-v2, a lightweight but effective sentence transformer that produces 384-dimensional vectors. ChromaDB uses HNSW indexing for fast approximate nearest neighbor search. Typical storage is 1-5 MB per video, making it very efficient.
-->

---

# Knowledge Store Architecture

**Document Metadata Schema:**

```json
{
  "video_id": "uuid",
  "section_id": "uuid",
  "type": "knowledge_point",
  "title": "Gradient Descent Basics",
  "begin_time": 120.5,
  "end_time": 180.0,
  "importance": 0.85
}
```

**Key Operations:**

1. **Upsert (during processing):**
```python
store.upsert(
    id="kp-uuid",
    text="Gradient Descent: Optimization algorithm...",
    metadata={...}
)
```

2. **Query (at chat time):**
```python
results = store.query(
    query_text="What is backpropagation?",
    video_id="uuid",
    top_k=5
)
# Returns: [{id, text, metadata, distance, relevance}]
```

<!--
Speaker Notes:
Each document in our vector store includes rich metadata. This enables filtered retrieval - for example, searching within a specific video or filtering by content type. The upsert operation happens during the async task pipeline, specifically in task 7 (embed knowledge). At chat time, we query the vector store with the user's question, scoped to the relevant video. Results include both the embedding distance and a computed relevance score. This metadata is crucial for building proper citations in our chatbot responses.
-->

---

# RAG Engine: Retrieval-Augmented Generation

**Two Operating Modes:**

| Mode | Endpoint | Latency | Use Case |
|------|----------|---------|----------|
| **Quick RAG** | `/api/videos/<id>/chat/stream/` | 2-5s | Factual questions |
| **Agent** | `/api/videos/<id>/agent/stream/` | 5-15s | Complex reasoning |

**Quick RAG Pipeline:**
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

<!--
Speaker Notes:
Our RAG system operates in two modes. Quick RAG is a single-shot retrieval and generation pipeline, perfect for factual questions with clear answers in the lecture. The Agent mode uses a ReAct loop for multi-step reasoning, which my teammate will explain in detail. In Quick RAG, we embed the question, search the vector store, filter low-relevance results, and build a context-augmented prompt. We also inject the lecture summary as background context. The LLM then generates a grounded answer with citations. The entire process takes 2-5 seconds with streaming.
-->

---

# RAG Prompt Engineering

**System Prompt:**
```
You are a knowledgeable teaching assistant for a video lecture.
Answer the student's question based on the lecture content provided.

Instructions:
- Answer ONLY based on the provided context
- Cite sources using [Source N] notation
- Be concise but thorough, use markdown formatting
- Maintain an educational, helpful tone
```

**Context Template:**
```markdown
## Lecture Context

### Video: {video_title}

### Lecture Overview
{summary_section}

### Retrieved Sources:
[Source 1] (knowledge_point) "Gradient Descent" [02:00-03:00] (relevance: 0.85)
Gradient descent is an optimization algorithm...

[Source 2] (section_transcript) "Learning Rate" [05:00-06:30] (relevance: 0.72)
The learning rate controls the step size...

---
Student Question: {question}
```

<!--
Speaker Notes:
Prompt engineering is critical for RAG quality. Our system prompt establishes the assistant's role and constraints. We explicitly instruct the LLM to answer only from provided context and to cite sources. The context template structures the retrieved information with clear formatting. Each source includes its type, title, timestamp range, and relevance score. This structured format helps the LLM understand which sources are most relevant and where they appear in the video. We also include the lecture overview summary, which provides broad context even when specific retrieved sources don't cover the topic.
-->

---

# Agent System: ReAct Multi-Step Reasoning

**For complex questions requiring multiple information sources:**

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
│  5. Repeat until final response     │
└─────────────────────────────────────┘
     │
     ▼
Stream answer + tool steps + citations
```

**Available Tools:**
- `search_knowledge(query)` - Vector search
- `get_section_details(section_order)` - Full section content
- `get_lecture_summary()` - Overview + chapters
- `list_sections()` - All section titles/times
- `get_transcript_at_time(start, end)` - Transcript slice

<!--
Speaker Notes:
The Agent mode implements a ReAct loop - Reasoning plus Acting. Instead of a single retrieval, the LLM can iteratively consult different tools. For example, a question like "Compare how gradient descent is explained in the first half versus the second half" requires multiple steps: first identifying relevant sections, then retrieving details from each, then synthesizing a comparison. The LLM decides which tool to call at each step, with a maximum of 5 iterations to prevent infinite loops. This architecture enables sophisticated reasoning that simple RAG cannot achieve.
-->

---

# Agent Execution Example

**Question:** *"How does the lecture explain the relationship between learning rate and convergence?"*

**Execution Trace:**
```
Step 1: thinking — "Analyzing question (step 1)..."
Step 2: tool_call — search_knowledge(query="learning rate convergence")
Step 3: tool_result — "[Result 1] (knowledge_point) 'Learning Rate...' ..."
Step 4: thinking — "Analyzing question (step 2)..."
Step 5: tool_call — get_section_details(section_order=3)
Step 6: tool_result — "## Section 3: Optimization Techniques..."
Step 7: thinking — "Composing answer..."
Step 8-N: token — "The lecture explains that the learning rate..."
Final: citations — [{source_num: 1, title: "Learning Rate", begin_time: 180, ...}]
Final: done — {tool_steps: [...]}
```

**SSE Stream Events:**
- `thinking` - Reasoning steps
- `tool_call` - Tool invocations
- `tool_result` - Tool outputs (300-char preview)
- `token` - Answer text chunks
- `citations` - Structured citation list
- `done` - Completion signal

<!--
Speaker Notes:
Here's a real execution trace. The agent first calls search_knowledge to find relevant content about learning rate and convergence. After seeing the results, it decides to get more detailed information from a specific section. Only after gathering sufficient context does it compose the final answer. Throughout this process, we stream events to the frontend using Server-Sent Events. This provides immediate feedback to the user - they see the thinking process, tool calls, and then the streaming answer. The citations are extracted from tool results and linked to specific timestamps, enabling click-to-seek functionality.
-->

---

# Citation Schema & Frontend Integration

**Citation Structure:**
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

**Frontend Rendering:**
- Clickable citation badges: `[Source 1]`
- Click → seek video to `begin_time`
- Hover → show preview tooltip
- Color-coded by type (knowledge point vs transcript)

**Multi-Turn Context:**
- Last 6 messages included in prompt
- Enables follow-up questions: "Can you explain that more?"
- Session persisted in database

<!--
Speaker Notes:
Citations are crucial for trust and verification. Each citation includes the source number matching the LLM's [Source N] references, the title, timestamp range, content type, and relevance score. The frontend renders these as clickable badges. When a student clicks a citation, the video seeks to that timestamp, allowing them to verify the answer directly. We also support multi-turn conversations by including the last 6 messages in the prompt. This enables natural follow-up questions and clarifications. All sessions are persisted, so students can return to previous conversations.
-->

---

<!-- _class: lead -->

# Part 3: Implementation & Results

## Speaker 3

<!--
Speaker Notes:
My teammate will now discuss our implementation details, challenges we faced, and the results we've achieved.
-->

---

# Async Task Pipeline Architecture

**DAG Executor with Dependency Resolution:**

```python
class AsyncTaskItem(models.Model):
    task_type = CharField(...)  # e.g., "task_ssim_move_detection"
    status = CharField(...)     # pending, running, success, error
    previous = ForeignKey(...)  # Dependency (null = no deps)
    input_data = JSONField()
    result_data = JSONField()
    error_message = TextField()
```

**Task Processor:**
- Polls every 5 seconds for pending tasks
- `SELECT FOR UPDATE SKIP LOCKED` for concurrent safety
- Chains outputs: `task[n].result` → `task[n+1].input`
- Cascade failure: downstream tasks auto-marked as error
- Retry mechanism: reset failed task + descendants

<!--
Speaker Notes:
Our async task pipeline is a custom DAG executor built on Django. Each task record includes its type, status, dependency reference, and data payloads. The task processor is a management command that runs continuously, polling for pending tasks whose dependencies are satisfied. We use row-level locking with SKIP LOCKED to support multiple concurrent workers safely. When a task completes, its result is automatically merged into the next task's input. If a task fails, all downstream tasks are marked with cascade failure, preventing wasted computation. Failed tasks can be retried, which also resets all blocked descendants.
-->

---

# LLM Integration: Qwen Family

**Models Used:**

| Task | Model | Temperature | Purpose |
|------|-------|-------------|---------|
| ASR Transcription | Qwen3-ASR | N/A | Speech-to-text |
| Knowledge Extraction | qwen2.5-7b-instruct | 0.3 | Structured JSON |
| Coarse Summary | qwen2.5-7b-instruct | 0.5 | Lecture overview |
| Mindmap Generation | qwen2.5-7b-instruct | 0.5 | Hierarchy structure |
| RAG Answer | qwen3-max | 0.5 | Grounded response |
| Agent Reasoning | qwen3-max | 0.3 | Tool selection |

**LLM Client Abstraction:**
```python
class LLMClient:
    def chat(self, messages, temperature=0.5, max_tokens=2048)
    def stream_chat(self, messages, tools=None)  # Function calling
```

<!--
Speaker Notes:
We leverage multiple models from Alibaba's Qwen family, each selected for its strengths. Qwen3-ASR handles speech recognition with sentence-level timestamps. For knowledge extraction and summarization, we use qwen2.5-7b-instruct - a good balance of capability and cost. For RAG answers and agent reasoning, we use qwen3-max, the most capable model with excellent function-calling support. Temperature is tuned per task: lower for structured output (0.3), higher for creative generation (0.5). Our LLM client provides a clean abstraction with OpenAI-compatible APIs, making it easy to swap models if needed.
-->

---

# Knowledge Point Extraction Quality

**Prompt Template:**
```
You are an expert educational content analyst. Analyze the lecture segment
and extract structured knowledge points.

Section: {section_title}
Time range: {time_range}
Transcript:
---
{transcript}
---

Extract in JSON format:
{
  "section_title": "Concise title (5-10 words)",
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

**Output Quality Controls:**
- Truncate transcript to 3000 chars (focus on key content)
- Skip sections with < 20 chars (silence-only segments)
- Error isolation: continue on individual section failures
- Logging: all LLM calls saved for debugging

<!--
Speaker Notes:
Quality knowledge extraction depends heavily on prompt engineering. Our prompt establishes the expert persona, provides clear context with section title and time range, and specifies the exact JSON schema expected. We truncate transcripts to 3000 characters to focus on key content and stay within token limits. Sections with minimal transcript text are skipped as they likely contain only silence. We also implement error isolation - if one section fails, the task continues with remaining sections rather than failing entirely. All LLM calls are logged with full request/response details for debugging and quality analysis.
-->

---

# Mindmap Generation

**Purpose:** Visual hierarchy of lecture concepts

**Generation Pipeline:**
```
KnowledgeSummary.chapter_outline
     +
All KnowledgePoints (grouped by section)
     │
     ▼
LLM Prompt: "Build hierarchical concept map"
     │
     ▼
Parse JSON response:
{
  "root": {
    "id": "root",
    "label": "Introduction to Machine Learning",
    "children": [
      {
        "id": "ch1",
        "label": "Supervised Learning",
        "time_range": [0, 600],
        "children": [
          {"id": "kp1", "label": "Linear Regression", "time_range": [60, 180]},
          {"id": "kp2", "label": "Classification", "time_range": [180, 360]}
        ]
      }
    ]
  }
}
```

<!--
Speaker Notes:
The mindmap provides a visual overview of the lecture's concept hierarchy. We gather the chapter outline from the coarse-grained summary and all knowledge points grouped by section. The LLM is prompted to build a hierarchical tree structure with nodes labeled by concept names and annotated with time ranges. This JSON structure is then rendered in the frontend using React Flow, an interactive graph visualization library. Students can click any node to seek to the relevant video timestamp, zoom and pan for large maps, and collapse/expand branches. This transforms the linear video into an explorable knowledge graph.
-->

---

# Technical Challenges & Solutions

| Challenge | Solution |
|-----------|----------|
| **Memory constraints** (8GB systems) | Disabled semantic similarity check in chunking |
| **LLM JSON parsing errors** | Robust parser handles fenced JSON, embedded JSON, raw JSON |
| **Cascade failures in DAG** | Automatic downstream error marking + retry resets all |
| **Concurrent task processing** | `SELECT FOR UPDATE SKIP LOCKED` row-level locking |
| **Long video processing** | Frame sampling at 10 FPS, multithreaded SSIM |
| **Grounded RAG answers** | Strict system prompt + relevance filtering + citations |

<!--
Speaker Notes:
We faced several technical challenges during development. Memory constraints on 8GB systems forced us to disable the semantic similarity check in hybrid chunking. LLM responses sometimes included markdown fencing or prose around the JSON, so we built a robust parser that handles multiple formats. Cascade failures in the DAG were problematic early on, but we implemented automatic error propagation and a retry mechanism that resets all blocked descendants. Concurrent task processing required careful database locking to prevent race conditions. Long videos were addressed through frame sampling and multithreading. Finally, ensuring RAG answers are grounded in the lecture content required careful prompt engineering and relevance filtering.
-->

---

# Results & Demo

**Typical Processing Output** (60-minute lecture):

| Metric | Value |
|--------|-------|
| Slide transitions detected | 12-18 |
| Sections created | 8-12 |
| Knowledge points extracted | 25-40 |
| Processing time | 5-8 minutes |
| Vector store size | 2-4 MB |

**RAG Performance:**
- Quick RAG latency: 2-5 seconds
- Agent latency: 5-15 seconds
- Citation accuracy: >90% (sources match answer content)

**Demo:** [Live demonstration of upload → processing → chat]

<!--
Speaker Notes:
Here are our typical results for a 60-minute lecture. We detect 12-18 slide transitions, create 8-12 sections, and extract 25-40 knowledge points. Total processing time is 5-8 minutes, with most time spent on LLM calls. The vector store is compact at 2-4 MB per video. RAG performance is excellent with 2-5 second latency for quick questions and 5-15 seconds for complex agent reasoning. Citation accuracy exceeds 90%, meaning the sources referenced in answers genuinely support the content. We'd now like to show a live demo of the complete workflow from upload to chat interaction.
-->

---

# Future Work

**Planned Enhancements:**

1. **Multi-video Course RAG**
   - Cross-lecture queries: "Compare gradient descent in Lectures 1 and 3"
   - Course-level knowledge aggregation

2. **Improved Chunking**
   - Re-enable semantic similarity with optimized model
   - Speaker change detection for multi-instructor lectures

3. **Enhanced Agent Tools**
   - `compare_concepts(concept_a, concept_b)` - Direct comparison tool
   - `summarize_range(video_id, start, end)` - On-demand summarization

4. **Production Deployment**
   - PostgreSQL migration (from SQLite)
   - Docker Compose setup
   - User authentication & authorization

<!--
Speaker Notes:
Looking ahead, we have several exciting enhancements planned. Multi-video course RAG will enable cross-lecture queries, allowing students to compare how concepts are explained across different lectures. We plan to re-enable semantic similarity chunking with a more memory-efficient model. The agent system will gain new tools for direct concept comparison and on-demand summarization of specific time ranges. For production deployment, we'll migrate from SQLite to PostgreSQL for better concurrent write support, containerize with Docker Compose, and add user authentication. These improvements will make LectureMind a robust, production-ready educational platform.
-->

---

# Summary

**LectureMind transforms lecture videos into interactive learning experiences through:**

1. **Automated Preprocessing**
   - SSIM slide detection (multithreaded, efficient)
   - Hybrid chunking (slide + silence + semantic)
   - ASR transcription with timestamps

2. **AI Knowledge Extraction**
   - Fine-grained: Per-section knowledge points via LLM
   - Coarse-grained: Lecture-level summaries and chapters
   - Mindmap: Hierarchical concept visualization

3. **Intelligent Q&A**
   - Quick RAG: Fast, factual answers (2-5s)
   - Agent mode: Multi-step reasoning (5-15s)
   - Grounded answers with timestamp citations

**Thank you! Questions?**

<!--
Speaker Notes:
To summarize, LectureMind transforms passive lecture videos into interactive learning experiences. Our automated preprocessing handles slide detection, intelligent chunking, and transcription. AI knowledge extraction produces both fine-grained knowledge points and coarse-grained summaries, visualized as an interactive mindmap. The RAG system enables intelligent Q&A with both fast factual answers and sophisticated multi-step reasoning. All answers are grounded in actual lecture content with clickable citations. We've built a complete end-to-end system that makes lecture content searchable, navigable, and conversational. Thank you for your attention. We're happy to take any questions.
-->
