"""
RAG Evaluation Module for LectureMind.

This module provides comprehensive evaluation capabilities for comparing
different RAG approaches: LLM Direct, Fast RAG, and Agentic RAG.

Usage:
    from api.evaluate import RAGEvaluator

    evaluator = RAGEvaluator(video_id="uuid")
    report = evaluator.run_evaluation(num_questions=20)
    report.save("/path/to/report.json")
"""

from .evaluator import RAGEvaluator
from .report import EvaluationReport

__all__ = ["RAGEvaluator", "EvaluationReport"]
