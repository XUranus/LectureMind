# RAG Evaluation Module

This document describes the RAG Evaluation Module for LectureMind, which provides
comprehensive evaluation capabilities for comparing the three RAG approaches and
measuring hallucination reduction.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Module Structure](#2-module-structure)
3. [Workflow](#3-workflow)
4. [Usage](#4-usage)
5. [RAG Modes](#5-rag-modes)
6. [Dataset Generation](#6-dataset-generation)
7. [Judge System](#7-judge-system)
8. [Evaluation Metrics](#8-evaluation-metrics)
9. [Output Files](#9-output-files)
10. [Dataset Format](#10-dataset-format)
11. [Interpreting Results](#11-interpreting-results)
12. [Example Output](#12-example-output)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Overview

The evaluation module compares three RAG modes:

| Mode | Description | Baseline |
|---|---|---|
| **LLM Direct** | Pure LLM response — no retrieval | Yes (hallucination reference) |
| **Fast RAG** | Single-pass vector retrieval + generation | No |
| **Agentic RAG** | Multi-step LangGraph agent with tool calls | No |

Goals:
- Quantify how much each RAG mode reduces hallucination vs. the LLM Direct baseline
- Identify systematic failure patterns (poor retrieval, missing tools, OCR gaps)
- Support custom question injection for targeted testing

---

## 2. Module Structure

```
api/evaluate/
├── __init__.py              # Module exports
├── models.py                # EvaluationResult, QAPair, AggregateMetrics data classes
├── dataset_generator.py     # SOTA model generates Q&A pairs + irrelevant questions
├── rag_modes.py             # LLMDirectMode, FastRAGMode, AgenticRAGMode
├── judge.py                 # SOTA model judges each response vs. ground truth
├── evaluator.py             # Orchestrator: generate → answer → judge → report
└── report.py                # JSON / CSV / Markdown / HTML report writers

api/management/commands/
└── evaluate_rag.py          # Django management command (CLI entry point)
```

---

## 3. Workflow

```
1. Dataset Generation
   └── SOTA model (qwen3.6-plus) analyses the video knowledge base
       (KnowledgePoint, KnowledgeSummary, VideoSection, SlideOCR)
       and generates N question-answer pairs:
         • ~70 % relevant questions (factual, conceptual, procedural)
         • ~30 % irrelevant questions (hallucination detection probes)

2. Response Generation
   └── For each question, all three RAG modes answer using the test model (qwen-turbo)
       Results are collected with timing and token usage.

3. Judge Evaluation
   └── SOTA model scores each response against ground truth:
         • Overall score (0-100)
         • Accuracy, completeness, relevance sub-scores
         • Hallucination flag + explanation

4. Report Generation
   └── Aggregate metrics, comparative analysis, and per-question breakdowns
       written to JSON / CSV / Markdown / HTML.
```

---

## 4. Usage

### Basic

```bash
cd server/app
python manage.py evaluate_rag --video <video-uuid>
```

### Full options

```bash
python manage.py evaluate_rag \
    --video <uuid>                        \  # required: video to evaluate
    --questions 20                         \  # total questions (generated + custom)
    --question "Who are the tutors?,What is the grading policy?"  \  # custom questions (comma-separated)
    --question_count 10                    \  # generate 10-2=8 additional questions
    --sota-model qwen3.6-plus              \  # model for generation + judging
    --test-model qwen-turbo                \  # model under test
    --output ./evaluation_reports/         \  # output directory
    --formats json,csv,md,html             \  # report formats
    --dataset ./existing_dataset.json      \  # skip generation, use saved dataset
    --save-dataset                         \  # save generated Q&A pairs to disk
    --no-irrelevant                        \  # disable irrelevant question injection
    --irrelevant-ratio 0.3                 \  # fraction of irrelevant questions (default 0.3)
    --verbose                                 # detailed logging
```

### Custom questions

The `--question` flag accepts comma-separated questions. Use `--question_count` to set
the total; the remainder are auto-generated:

```bash
# 2 custom + 8 generated = 10 total
python manage.py evaluate_rag \
    --video <uuid> \
    --question "Who are the tutors?,What is the email of the lecturer?" \
    --question_count 10
```

Custom questions are answered with the full knowledge base as context (transcript +
knowledge points + slide OCR), so the judge has accurate ground truth to compare against.

---

## 5. RAG Modes

### LLMDirectMode (`api/evaluate/rag_modes.py`)

- Sends the question directly to the LLM with no retrieval context
- Serves as the hallucination baseline
- No fallback needed

### FastRAGMode

- Queries ChromaDB for the top-k most relevant documents
- Applies two quality gates before generation:
  - `MIN_RELEVANCE_THRESHOLD = 0.3` — minimum cosine similarity
  - `MIN_DOCUMENTS_REQUIRED = 2` — minimum number of results above threshold
- **Fallback**: if quality gates fail, transparently falls back to LLM Direct and
  records `fallback_used = True` in the result

### AgenticRAGMode

- Runs the full `AgentRunner` (LangGraph state machine)
- Agent calls tools iteratively:
  - `search_knowledge` — semantic search over knowledge points, sections, transcripts
  - `get_section_detail` — full section content
  - `get_transcript_range` — raw transcript slice by timestamp
  - `search_slides` — slide OCR text (contact info, schedules, visual content)
- Citation sanitization removes hallucinated citation markers before scoring
- **Fallback chain**: Agentic → Fast RAG → LLM Direct (each level recorded)

---

## 6. Dataset Generation

### Relevant questions (~70 %)

Generated by the SOTA model from the video knowledge base:

| Type | Example |
|---|---|
| Factual recall | "What is the definition of X given in this lecture?" |
| Conceptual | "Explain the relationship between X and Y." |
| Procedural | "What steps are described for doing X?" |
| Metadata | "Who are the tutors for this course?" |

Each pair includes:
- `question`, `ground_truth_answer`
- `question_type`, `difficulty` (`easy` / `medium` / `hard`)
- `source_knowledge_ids` — which knowledge points ground the answer

### Irrelevant questions (~30 %, hallucination probes)

Generated by `_generate_irrelevant_questions()` in `dataset_generator.py`.
These questions have no correct answer in the knowledge base:

- Topics entirely outside the lecture content
- Questions about people or events not mentioned in the video
- Factually plausible-sounding but unsupported claims

Marked with `is_relevant: false` and `is_hallucination_test: true` in the dataset.

The judge is instructed to flag a response as hallucinating **only** if it asserts
false information — a correct "I don't know / this isn't covered" is scored positively.

### Extending the dataset

When `--question` provides K custom questions and `--question_count N` is set,
the generator produces `N - K` additional questions automatically. If `N` is not set,
only the K custom questions are evaluated.

---

## 7. Judge System

The judge (`api/evaluate/judge.py`) is called once per (question, mode, response) triple
using the SOTA model. It evaluates:

| Criterion | Description |
|---|---|
| **Accuracy** | Factual correctness vs. ground truth |
| **Completeness** | Coverage — did it address all aspects of the question? |
| **Relevance** | Is the response on-topic and specific to the question? |
| **Hallucination** | Does the response assert facts not supported by the knowledge base? |

**Judge prompt design:**
- Explicitly instructed not to penalise a fallback response (e.g. "I cannot find this in the lecture") as hallucination
- Instructed to recognise `INSUFFICIENT_INFO` ground truth answers as correct refusals
- Instructed to score irrelevant-question responses positively when the model correctly declines to answer

---

## 8. Evaluation Metrics

### Per-response

| Metric | Range | Description |
|---|---|---|
| `overall_score` | 0–100 | Weighted combination of sub-scores |
| `accuracy_score` | 0–100 | Factual correctness |
| `completeness_score` | 0–100 | Coverage of the question |
| `relevance_score` | 0–100 | On-topic specificity |
| `hallucination_detected` | bool | True if unsupported facts asserted |
| `hallucination_details` | str | Judge's explanation |
| `response_time_ms` | int | Wall-clock time in milliseconds |
| `fallback_used` | bool | Whether a fallback mode was triggered |

### Aggregate (per mode)

- Mean overall / accuracy / completeness / relevance scores
- Hallucination rate (% of responses flagged)
- Mean response time
- Error rate (exceptions during generation)
- Fallback rate (how often the mode fell back to a simpler one)

### Comparative

```
Hallucination Reduction =
    (Baseline_Hallucinations − Mode_Hallucinations) / Baseline_Hallucinations × 100 %
```

A positive value means the mode hallucinates less than LLM Direct.

---

## 9. Output Files

All files are written to `--output` (default: `./evaluation_reports/`).

| File | Format | Contents |
|---|---|---|
| `<eval_id>.json` | JSON | Complete evaluation — all questions, responses, scores |
| `<eval_id>.csv` | CSV | One row per (question, mode); spreadsheet-friendly |
| `<eval_id>.md` | Markdown | Human-readable report with tables and summaries |
| `<eval_id>.html` | HTML | Interactive report with per-question drill-down |
| `<eval_id>_comparison.json` | JSON | Aggregate comparison across modes |
| `<eval_id>_dataset.json` | JSON | Saved Q&A dataset (only with `--save-dataset`) |

---

## 10. Dataset Format

```json
{
  "video_id": "uuid",
  "generated_at": "2026-04-12T10:00:00Z",
  "sota_model": "qwen3.6-plus",
  "qa_pairs": [
    {
      "id": "uuid",
      "question": "What optimisation algorithm is introduced in section 3?",
      "ground_truth_answer": "Gradient descent is introduced...",
      "question_type": "factual",
      "difficulty": "easy",
      "is_relevant": true,
      "is_hallucination_test": false,
      "source_knowledge_ids": ["kp-uuid-1", "kp-uuid-2"],
      "metadata": {
        "topic": "Optimisation",
        "reasoning_required": "Direct recall"
      }
    },
    {
      "id": "uuid",
      "question": "What was the lecturer's opinion on quantum computing?",
      "ground_truth_answer": "INSUFFICIENT_INFO",
      "question_type": "out_of_scope",
      "difficulty": "medium",
      "is_relevant": false,
      "is_hallucination_test": true,
      "source_knowledge_ids": [],
      "metadata": {}
    }
  ]
}
```

---

## 11. Interpreting Results

### Hallucination reduction

The primary metric. A well-functioning RAG system should show:
- Fast RAG: 50–70 % reduction vs. LLM Direct
- Agentic RAG: 70–90 % reduction vs. LLM Direct

If Fast RAG shows little reduction, check:
- Whether the vector store is populated (`task_embed_knowledge` completed)
- Retrieval relevance scores (low scores → fallback to LLM Direct is frequent)
- `MIN_RELEVANCE_THRESHOLD` — may need tuning for the domain

If Agentic RAG underperforms Fast RAG, check:
- Whether `search_slides` was needed (metadata questions like tutor info, schedules)
- Citation sanitization logs for hallucinated references
- Agent tool selection logs (`--verbose`)

### Score improvements

| Score type | What a gap means |
|---|---|
| Accuracy gap (RAG vs Direct) | Knowledge base is providing correct facts |
| Completeness gap | RAG retrieves multiple relevant sections |
| Relevance drop | Over-retrieval — context is diluting the answer |

### Response time trade-offs

| Mode | Typical latency | Cause |
|---|---|---|
| LLM Direct | ~800 ms | Single LLM call |
| Fast RAG | ~1 200 ms | Embedding + ChromaDB query + LLM call |
| Agentic RAG | 2 000–5 000 ms | Multiple tool calls + LLM reasoning steps |

### Fallback rate

A high Fast RAG fallback rate (> 20 %) suggests the knowledge base is sparse or the
embedding model is a poor fit for the question vocabulary. Consider re-running
`task_embed_knowledge` or lowering `MIN_DOCUMENTS_REQUIRED`.

A high Agentic RAG fallback rate suggests the agent is timing out or the LLM is not
selecting tools correctly. Review the `AGENT_SYSTEM_PROMPT` in `agent_graph.py`.

---

## 12. Example Output

```
================================================================================
RAG EVALUATION SUMMARY
================================================================================
Video: Introduction to Machine Learning (uuid)
Questions: 20 (14 relevant + 6 hallucination probes)
SOTA Model: qwen3.6-plus  |  Test Model: qwen-turbo

────────────────────────────────────────────────────────────────────────────────
AGGREGATE METRICS
────────────────────────────────────────────────────────────────────────────────

                    LLM Direct    Fast RAG    Agentic RAG
Overall Score          45.2         78.5          85.3
Accuracy Score         42.1         80.3          87.1
Completeness Score     48.0         76.2          83.4
Relevance Score        60.3         79.0          85.8
Hallucination Rate     65.0 %       20.0 %        10.0 %
Avg Response Time      850 ms      1200 ms        3500 ms
Fallback Rate            —          12.0 %         5.0 %
Error Rate              0.0 %        0.0 %         0.0 %

────────────────────────────────────────────────────────────────────────────────
HALLUCINATION ANALYSIS
────────────────────────────────────────────────────────────────────────────────
LLM Direct      13 / 20  (65.0 %)
Fast RAG         4 / 20  (20.0 %)   → 69.2 % reduction
Agentic RAG      2 / 20  (10.0 %)   → 84.6 % reduction

================================================================================
```

---

## 13. Troubleshooting

### No knowledge base found

Ensure the video has completed all pipeline tasks:
- `task_hybrid_chunking` → `VideoSection` records exist
- `task_fine_grained_knowledge` → `KnowledgePoint` records exist
- `task_coarse_grained_summary` → `KnowledgeSummary` record exists
- `task_embed_knowledge` → ChromaDB collection populated

Check with:
```bash
python manage.py shell -c "
from api.models import Video, KnowledgePoint, KnowledgeSummary
v = Video.objects.get(id='<uuid>')
print('KP count:', KnowledgePoint.objects.filter(video=v).count())
print('Summary:', KnowledgeSummary.objects.filter(video=v).exists())
"
```

### Only custom questions evaluated (generated questions missing)

Pass `--question_count N` where N > number of custom questions. Without it, only
the custom questions are evaluated.

### Judge incorrectly flags correct answers as hallucination

This can happen when:
- The ground truth is `INSUFFICIENT_INFO` but the model answers correctly with a refusal
- A fallback response ("I cannot find this") is penalised

Both cases are handled by the judge prompt. If still occurring, increase `--sota-model`
quality or inspect the judge's `hallucination_details` field in the JSON report.

### Agentic RAG performs worse than Fast RAG on metadata questions

Add `search_slides` tool calls. The agent should prefer `search_slides` for questions
about tutors, contact info, schedules, and other visually-presented content. Verify
`SlideOCR` records exist for the video and that `task_slides_ocr` completed successfully.

### API rate limit errors

Reduce parallelism or add delays between requests. The evaluator uses
`ThreadPoolExecutor` internally — reduce worker count by setting the environment
variable `EVAL_MAX_WORKERS=2` (default: 4) before running the command.
