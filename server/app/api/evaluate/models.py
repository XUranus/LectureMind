"""
Data models for RAG evaluation.

These models store evaluation datasets, results, and metrics for analysis.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


class RAGMode(Enum):
    """Enumeration of RAG modes being evaluated."""
    LLM_DIRECT = "llm_direct"
    FAST_RAG = "fast_rag"
    AGENTIC_RAG = "agentic_rag"


class EvaluationStatus(Enum):
    """Status of an evaluation run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class QuestionAnswerPair:
    """A single question-answer pair generated from ground truth."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    question: str = ""
    ground_truth_answer: str = ""
    question_type: str = ""  # e.g., "factual", "conceptual", "procedural"
    difficulty: str = ""  # e.g., "easy", "medium", "hard"
    source_knowledge_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QuestionAnswerPair:
        return cls(**data)


@dataclass
class ModeResponse:
    """Response from a single RAG mode for a question."""
    mode: RAGMode
    answer: str = ""
    response_time_ms: float = 0.0
    tokens_used: int = 0
    citations: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "answer": self.answer,
            "response_time_ms": self.response_time_ms,
            "tokens_used": self.tokens_used,
            "citations": self.citations,
            "tool_calls": self.tool_calls,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ModeResponse:
        data = data.copy()
        data["mode"] = RAGMode(data["mode"])
        return cls(**data)


@dataclass
class JudgeEvaluation:
    """Evaluation result from the judge model for a single response."""
    mode: RAGMode
    overall_score: float = 0.0  # 0-100
    accuracy_score: float = 0.0  # 0-100
    completeness_score: float = 0.0  # 0-100
    hallucination_detected: bool = False
    hallucination_details: str = ""
    relevance_score: float = 0.0  # 0-100
    explanation: str = ""
    comparison_to_ground_truth: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "overall_score": self.overall_score,
            "accuracy_score": self.accuracy_score,
            "completeness_score": self.completeness_score,
            "hallucination_detected": self.hallucination_detected,
            "hallucination_details": self.hallucination_details,
            "relevance_score": self.relevance_score,
            "explanation": self.explanation,
            "comparison_to_ground_truth": self.comparison_to_ground_truth,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JudgeEvaluation:
        data = data.copy()
        data["mode"] = RAGMode(data["mode"])
        return cls(**data)


@dataclass
class QuestionResult:
    """Complete results for a single question across all modes."""
    qa_pair: QuestionAnswerPair
    responses: Dict[RAGMode, ModeResponse] = field(default_factory=dict)
    evaluations: Dict[RAGMode, JudgeEvaluation] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "qa_pair": self.qa_pair.to_dict(),
            "responses": {k.value: v.to_dict() for k, v in self.responses.items()},
            "evaluations": {k.value: v.to_dict() for k, v in self.evaluations.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> QuestionResult:
        qa_pair = QuestionAnswerPair.from_dict(data["qa_pair"])
        responses = {
            RAGMode(k): ModeResponse.from_dict(v)
            for k, v in data["responses"].items()
        }
        evaluations = {
            RAGMode(k): JudgeEvaluation.from_dict(v)
            for k, v in data["evaluations"].items()
        }
        return cls(qa_pair=qa_pair, responses=responses, evaluations=evaluations)


@dataclass
class AggregateMetrics:
    """Aggregate metrics across all questions for a single mode."""
    mode: RAGMode
    num_questions: int = 0
    avg_overall_score: float = 0.0
    avg_accuracy_score: float = 0.0
    avg_completeness_score: float = 0.0
    avg_relevance_score: float = 0.0
    hallucination_rate: float = 0.0  # percentage of responses with hallucination
    avg_response_time_ms: float = 0.0
    total_tokens_used: int = 0
    error_rate: float = 0.0  # percentage of questions with errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "num_questions": self.num_questions,
            "avg_overall_score": self.avg_overall_score,
            "avg_accuracy_score": self.avg_accuracy_score,
            "avg_completeness_score": self.avg_completeness_score,
            "avg_relevance_score": self.avg_relevance_score,
            "hallucination_rate": self.hallucination_rate,
            "avg_response_time_ms": self.avg_response_time_ms,
            "total_tokens_used": self.total_tokens_used,
            "error_rate": self.error_rate,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AggregateMetrics:
        data = data.copy()
        data["mode"] = RAGMode(data["mode"])
        return cls(**data)


@dataclass
class EvaluationRun:
    """Complete evaluation run data."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    video_id: str = ""
    video_title: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: EvaluationStatus = EvaluationStatus.PENDING
    sota_model: str = ""  # Model used for dataset generation and judging
    test_model: str = ""  # Model used for answering (weaker model)
    num_questions: int = 0
    question_results: List[QuestionResult] = field(default_factory=list)
    aggregate_metrics: Dict[RAGMode, AggregateMetrics] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "video_id": self.video_id,
            "video_title": self.video_title,
            "created_at": self.created_at,
            "status": self.status.value,
            "sota_model": self.sota_model,
            "test_model": self.test_model,
            "num_questions": self.num_questions,
            "question_results": [qr.to_dict() for qr in self.question_results],
            "aggregate_metrics": {k.value: v.to_dict() for k, v in self.aggregate_metrics.items()},
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvaluationRun:
        data = data.copy()
        data["status"] = EvaluationStatus(data["status"])
        data["question_results"] = [
            QuestionResult.from_dict(qr) for qr in data["question_results"]
        ]
        data["aggregate_metrics"] = {
            RAGMode(k): AggregateMetrics.from_dict(v)
            for k, v in data["aggregate_metrics"].items()
        }
        return cls(**data)
