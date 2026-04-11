# RAG Evaluation Module

This document describes the RAG (Retrieval-Augmented Generation) Evaluation Module for LectureMind, which provides comprehensive evaluation capabilities for comparing different RAG approaches.

## Overview

The evaluation module compares three RAG modes:

1. **LLM Direct**: Direct LLM response without any retrieval (baseline)
2. **Fast RAG**: Standard retrieval-augmented generation using vector search
3. **Agentic RAG**: Multi-step agent with tool use and reasoning

The goal is to demonstrate how the Agentic RAG system reduces hallucination compared to baseline approaches.

## Architecture

```
api/evaluate/
├── __init__.py              # Module exports
├── models.py                # Data models for evaluation
├── dataset_generator.py     # SOTA model generates Q&A pairs
├── rag_modes.py            # Three RAG mode implementations
├── judge.py                # SOTA model judges responses
├── evaluator.py            # Main evaluation orchestrator
└── report.py               # Report generation

api/management/commands/
└── evaluate_rag.py         # CLI command
```

## Workflow

1. **Dataset Generation**: Uses SOTA model (qwen3.6-plus) to analyze the knowledge base and generate ~20 question-answer pairs
2. **Response Generation**: Each RAG mode answers all questions using the test model (qwen-turbo)
3. **Judge Evaluation**: SOTA model evaluates each response against ground truth
4. **Report Generation**: Comprehensive reports with metrics and hallucination analysis

## Usage

### Basic Usage

```bash
cd server/app
python manage.py evaluate_rag --video <video-uuid>
```

### Advanced Options

```bash
# Custom number of questions
python manage.py evaluate_rag --video <uuid> --questions 30

# Custom models
python manage.py evaluate_rag --video <uuid> --sota-model qwen3.6-plus --test-model qwen-turbo

# Custom output directory
python manage.py evaluate_rag --video <uuid> --output ./my_reports/

# Use existing dataset
python manage.py evaluate_rag --video <uuid> --dataset ./my_dataset.json

# Save generated dataset
python manage.py evaluate_rag --video <uuid> --save-dataset

# Specific output formats
python manage.py evaluate_rag --video <uuid> --formats json,csv,md,html

# Verbose logging
python manage.py evaluate_rag --video <uuid> --verbose
```

## Output Files

The evaluation generates multiple report files:

- `{evaluation_id}.json` - Complete evaluation data
- `{evaluation_id}.csv` - Tabular results for analysis
- `{evaluation_id}.md` - Human-readable markdown report
- `{evaluation_id}.html` - Interactive HTML report
- `{evaluation_id}_comparison.json` - Comparative analysis

## Evaluation Metrics

### Per-Response Metrics

- **Overall Score** (0-100): Weighted combination of all factors
- **Accuracy Score** (0-100): Factual correctness vs ground truth
- **Completeness Score** (0-100): Coverage of the question
- **Relevance Score** (0-100): Relevance to the specific question
- **Hallucination Detection**: Boolean flag with details

### Aggregate Metrics

- Average scores across all questions per mode
- Hallucination rate (percentage of responses with hallucination)
- Average response time
- Total tokens used
- Error rate

### Comparative Analysis

- Hallucination reduction percentage
- Score improvements over baseline
- Performance by question difficulty
- Performance by question type

## Dataset Format

When saving or loading datasets, the JSON format is:

```json
{
  "qa_pairs": [
    {
      "id": "uuid",
      "question": "What is gradient descent?",
      "ground_truth_answer": "Gradient descent is an optimization algorithm...",
      "question_type": "conceptual",
      "difficulty": "medium",
      "source_knowledge_ids": ["kp-1", "kp-2"],
      "metadata": {
        "topic": "Optimization",
        "reasoning_required": "Understanding of derivatives and optimization"
      }
    }
  ]
}
```

## Implementation Details

### Dataset Generator

Uses a SOTA model to generate diverse questions:
- Factual recall questions
- Conceptual understanding questions
- Procedural application questions
- Varying difficulty levels (easy, medium, hard)

### RAG Modes

**LLM Direct Mode**
- No retrieval context
- Tests baseline hallucination without knowledge base

**Fast RAG Mode**
- Uses existing `RAGEngine` class
- Vector search with top-k retrieval
- Single-pass generation

**Agentic RAG Mode**
- Uses existing `AgentRunner` class
- Multi-step reasoning with tool calls
- Can search, retrieve sections, get summaries

### Judge System

Evaluates responses using multiple criteria:
- Compares against ground truth
- Detects hallucinations (fabricated information)
- Scores accuracy, completeness, relevance
- Provides detailed explanations

## Interpreting Results

### Hallucination Reduction

The key metric is hallucination reduction:

```
Hallucination Reduction = (Baseline_Hallucinations - RAG_Hallucinations) / Baseline_Hallucinations * 100%
```

A positive reduction indicates the RAG system produces fewer hallucinations than the baseline LLM Direct mode.

### Score Improvements

Look for improvements in:
- Overall score: General quality improvement
- Accuracy score: Factual correctness improvement
- Completeness score: Better coverage of topics

### Response Time Trade-offs

Compare response times:
- LLM Direct: Fastest (no retrieval)
- Fast RAG: Moderate (single retrieval)
- Agentic RAG: Slowest (multiple tool calls)

## Requirements

- Django environment with LectureMind models
- API keys for LLM services (DashScope)
- Processed video with knowledge base (KnowledgePoint, KnowledgeSummary)
- ChromaDB vector store populated with embeddings

## Troubleshooting

### No Knowledge Base Found

Ensure the video has been processed and has:
- KnowledgeSummary
- KnowledgePoint entries
- VideoSection entries

### API Errors

Check:
- DASHSCOPE_API_KEY environment variable
- Model availability (qwen3.6-plus, qwen-turbo)
- API rate limits

### Empty Results

Verify:
- Vector store is populated
- Video ID is correct
- Knowledge base exists for the video

## Example Output

```
================================================================================
RAG EVALUATION SUMMARY
================================================================================
Video: Introduction to Machine Learning
Questions Evaluated: 20
SOTA Model: qwen3.6-plus
Test Model: qwen-turbo

--------------------------------------------------------------------------------
AGGREGATE METRICS
--------------------------------------------------------------------------------

LLM_DIRECT:
  Average Overall Score: 45.2/100
  Average Accuracy: 42.1/100
  Hallucination Rate: 65.0%
  Average Response Time: 850ms
  Error Rate: 0.0%

FAST_RAG:
  Average Overall Score: 78.5/100
  Average Accuracy: 80.3/100
  Hallucination Rate: 20.0%
  Average Response Time: 1200ms
  Error Rate: 0.0%

AGENTIC_RAG:
  Average Overall Score: 85.3/100
  Average Accuracy: 87.1/100
  Hallucination Rate: 10.0%
  Average Response Time: 3500ms
  Error Rate: 0.0%

--------------------------------------------------------------------------------
HALLUCINATION ANALYSIS
--------------------------------------------------------------------------------
LLM Direct Hallucinations: 13/20 (65.0%)
Fast RAG Hallucinations: 4/20 (20.0%)
Agentic RAG Hallucinations: 2/20 (10.0%)

Fast RAG Hallucination Reduction: 69.2%
Agentic RAG Hallucination Reduction: 84.6%

================================================================================
```

## Future Enhancements

Potential improvements:
- Support for additional RAG modes
- Custom evaluation criteria
- Batch evaluation across multiple videos
- Statistical significance testing
- Integration with experiment tracking (MLflow, W&B)
