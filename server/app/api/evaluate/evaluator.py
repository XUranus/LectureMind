"""
Main evaluation orchestrator for RAG systems.

Coordinates the full evaluation pipeline:
1. Dataset generation
2. Running all RAG modes (with multithreading)
3. Judge evaluation
4. Metrics aggregation

Supports concurrent execution for improved performance.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
from functools import partial

from api.evaluate.models import (
    RAGMode,
    EvaluationRun,
    EvaluationStatus,
    QuestionAnswerPair,
    QuestionResult,
    ModeResponse,
    JudgeEvaluation,
    AggregateMetrics,
)
from api.evaluate.dataset_generator import DatasetGenerator
from api.evaluate.rag_modes import RAGModeFactory, BaseRAGMode
from api.evaluate.judge import JudgeSystem, ComparativeAnalyzer
from api.models import Video

logger = logging.getLogger('LectureMind')


class RAGEvaluator:
    """
    Main orchestrator for RAG evaluation with multithreading support.

    Runs the complete evaluation pipeline and generates comprehensive reports.
    Supports concurrent execution of RAG modes and parallel question processing.
    """

    def __init__(
        self,
        video_id: str,
        sota_model: str = "qwen3.6-plus",
        test_model: str = "qwen-turbo",
        max_workers: int = 3,
        parallel_questions: bool = False,
        question_workers: int = 4,
        include_irrelevant_questions: bool = True,
        irrelevant_ratio: float = 0.3,
    ):
        """
        Initialize the RAG evaluator.

        Args:
            video_id: UUID of the video to evaluate
            sota_model: High-quality model for dataset generation and judging
            test_model: Weaker model for answering questions
            max_workers: Max threads for running RAG modes concurrently per question
            parallel_questions: Whether to process questions in parallel
            question_workers: Max threads for parallel question processing
            include_irrelevant_questions: Whether to include questions not answerable from KB
            irrelevant_ratio: Ratio of irrelevant questions (default 0.3 = 30%)
        """
        self.video_id = video_id
        self.sota_model = sota_model
        self.test_model = test_model
        self.max_workers = max_workers
        self.parallel_questions = parallel_questions
        self.question_workers = question_workers
        self.include_irrelevant_questions = include_irrelevant_questions
        self.irrelevant_ratio = irrelevant_ratio

        # Initialize components
        self.dataset_generator = DatasetGenerator(sota_model=sota_model)
        self.judge_system = JudgeSystem(sota_model=sota_model)
        self.comparative_analyzer = ComparativeAnalyzer()

        # Get video info
        try:
            self.video = Video.objects.get(id=video_id)
            self.video_title = self.video.title
        except Video.DoesNotExist:
            raise ValueError(f"Video {video_id} not found")

        logger.info(
            f"Initialized RAGEvaluator for video '{self.video_title}' "
            f"(SOTA: {sota_model}, Test: {test_model}, "
            f"Mode Workers: {max_workers}, Parallel Questions: {parallel_questions}, "
            f"Irrelevant Questions: {include_irrelevant_questions} @ {irrelevant_ratio:.0%})"
        )

    def run_evaluation(
        self,
        num_questions: int = 20,
        qa_pairs: Optional[List[QuestionAnswerPair]] = None,
    ) -> EvaluationRun:
        """
        Run the complete evaluation pipeline with multithreading.

        Args:
            num_questions: Number of Q&A pairs to generate (if not provided)
            qa_pairs: Optional pre-generated Q&A pairs to use

        Returns:
            EvaluationRun with complete results
        """
        start_time = time.time()

        # Initialize evaluation run
        evaluation_run = EvaluationRun(
            video_id=self.video_id,
            video_title=self.video_title,
            sota_model=self.sota_model,
            test_model=self.test_model,
            num_questions=num_questions,
            status=EvaluationStatus.RUNNING,
            metadata={
                "max_workers": self.max_workers,
                "parallel_questions": self.parallel_questions,
                "question_workers": self.question_workers,
            }
        )

        logger.info(f"Starting evaluation run {evaluation_run.id}")

        try:
            # Step 1: Generate or use provided dataset
            if qa_pairs is None:
                logger.info("Generating evaluation dataset...")
                qa_pairs = self.dataset_generator.generate_dataset(
                    video_id=self.video_id,
                    num_questions=num_questions,
                    include_irrelevant=self.include_irrelevant_questions,
                    irrelevant_ratio=self.irrelevant_ratio,
                )
            elif len(qa_pairs) < num_questions:
                # Generate additional questions to reach the desired total
                additional_needed = num_questions - len(qa_pairs)
                logger.info(f"Generating {additional_needed} additional questions to reach {num_questions} total...")
                additional_qa_pairs = self.dataset_generator.generate_dataset(
                    video_id=self.video_id,
                    num_questions=additional_needed,
                    include_irrelevant=self.include_irrelevant_questions,
                    irrelevant_ratio=self.irrelevant_ratio,
                )
                if additional_qa_pairs:
                    qa_pairs = qa_pairs + additional_qa_pairs
                    logger.info(f"Combined {len(qa_pairs)} total questions ({len(qa_pairs) - len(additional_qa_pairs)} custom + {len(additional_qa_pairs)} generated)")

            if not qa_pairs:
                raise ValueError("No Q&A pairs generated or provided")

            evaluation_run.num_questions = len(qa_pairs)
            logger.info(f"Evaluating with {len(qa_pairs)} questions")

            # Step 2: Evaluate questions (sequential or parallel)
            if self.parallel_questions:
                logger.info(f"Processing questions in parallel with {self.question_workers} workers...")
                evaluation_run.question_results = self._evaluate_questions_parallel(qa_pairs)
            else:
                logger.info("Processing questions sequentially...")
                evaluation_run.question_results = self._evaluate_questions_sequential(qa_pairs)

            # Step 3: Calculate aggregate metrics
            logger.info("Calculating aggregate metrics...")
            evaluation_run.aggregate_metrics = self._calculate_aggregate_metrics(
                evaluation_run.question_results
            )

            # Step 4: Mark as completed
            evaluation_run.status = EvaluationStatus.COMPLETED
            total_time = time.time() - start_time
            evaluation_run.metadata["total_duration_seconds"] = total_time
            logger.info(f"Evaluation run {evaluation_run.id} completed successfully in {total_time:.1f}s")

        except Exception as e:
            logger.exception(f"Evaluation failed: {e}")
            evaluation_run.status = EvaluationStatus.FAILED
            evaluation_run.metadata["error"] = str(e)

        return evaluation_run

    def _evaluate_questions_sequential(
        self,
        qa_pairs: List[QuestionAnswerPair],
    ) -> List[QuestionResult]:
        """
        Evaluate questions sequentially (original behavior).

        Args:
            qa_pairs: List of question-answer pairs

        Returns:
            List of QuestionResult objects
        """
        results = []

        for i, qa_pair in enumerate(qa_pairs, 1):
            logger.info(f"Processing question {i}/{len(qa_pairs)}: {qa_pair.question[:60]}...")

            question_result = self._evaluate_single_question_parallel_modes(qa_pair)
            results.append(question_result)

        return results

    def _evaluate_questions_parallel(
        self,
        qa_pairs: List[QuestionAnswerPair],
    ) -> List[QuestionResult]:
        """
        Evaluate questions in parallel using ThreadPoolExecutor.

        Args:
            qa_pairs: List of question-answer pairs

        Returns:
            List of QuestionResult objects
        """
        results = [None] * len(qa_pairs)

        with ThreadPoolExecutor(max_workers=self.question_workers) as executor:
            # Submit all questions for parallel processing
            future_to_index = {
                executor.submit(self._evaluate_single_question_parallel_modes, qa_pair): i
                for i, qa_pair in enumerate(qa_pairs)
            }

            # Collect results as they complete
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    result = future.result()
                    results[idx] = result
                    logger.info(f"Completed question {idx + 1}/{len(qa_pairs)}")
                except Exception as e:
                    logger.error(f"Question {idx + 1} failed: {e}")
                    # Create a failed result
                    results[idx] = QuestionResult(
                        qa_pair=qa_pairs[idx],
                        responses={},
                        evaluations={},
                    )

        return results

    def _evaluate_single_question_parallel_modes(
        self,
        qa_pair: QuestionAnswerPair,
    ) -> QuestionResult:
        """
        Evaluate a single question across all RAG modes with parallel execution.

        Args:
            qa_pair: The question-answer pair

        Returns:
            QuestionResult with all responses and evaluations
        """
        question_result = QuestionResult(qa_pair=qa_pair)

        # Create fresh RAG mode instances for this question (thread-safe)
        rag_modes = RAGModeFactory.get_all_modes(
            video_id=self.video_id,
            model=self.test_model,
        )

        # Run RAG modes in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all mode executions
            future_to_mode = {
                executor.submit(mode.answer, qa_pair.question): mode
                for mode in rag_modes
            }

            # Collect results as they complete
            for future in as_completed(future_to_mode):
                mode = future_to_mode[future]
                try:
                    response = future.result()
                    question_result.responses[mode.mode] = response
                    logger.debug(f"  {mode.mode.value} completed")
                except Exception as e:
                    logger.error(f"  {mode.mode.value} failed: {e}")
                    # Create a failed response
                    from api.evaluate.models import ModeResponse
                    question_result.responses[mode.mode] = ModeResponse(
                        mode=mode.mode,
                        answer="",
                        error=str(e),
                    )

        # Evaluate all responses with judge (sequential - judge calls are typically rate-limited)
        logger.debug(f"  Judging responses...")
        evaluations = self.judge_system.evaluate_all_modes(
            qa_pair=qa_pair,
            responses=question_result.responses,
        )
        question_result.evaluations = evaluations

        return question_result

    def _evaluate_single_question(
        self,
        qa_pair: QuestionAnswerPair,
        rag_modes: List,
    ) -> QuestionResult:
        """
        Evaluate a single question across all RAG modes (sequential fallback).

        Args:
            qa_pair: The question-answer pair
            rag_modes: List of RAG mode instances

        Returns:
            QuestionResult with all responses and evaluations
        """
        return self._evaluate_single_question_parallel_modes(qa_pair)

    def _calculate_aggregate_metrics(
        self,
        question_results: List[QuestionResult],
    ) -> Dict[RAGMode, AggregateMetrics]:
        """
        Calculate aggregate metrics across all questions for each mode.

        Args:
            question_results: List of question results

        Returns:
            Dictionary mapping RAG modes to their aggregate metrics
        """
        aggregate_metrics = {}

        for mode in RAGMode:
            # Collect all evaluations for this mode
            evaluations = []
            response_times = []
            tokens_used = []
            errors = 0

            for qr in question_results:
                if mode in qr.evaluations:
                    eval_data = qr.evaluations[mode]
                    evaluations.append(eval_data)

                    if mode in qr.responses:
                        response = qr.responses[mode]
                        response_times.append(response.response_time_ms)
                        tokens_used.append(response.tokens_used)
                        if response.error:
                            errors += 1

            if not evaluations:
                continue

            # Calculate averages
            num_questions = len(evaluations)
            avg_overall = sum(e.overall_score for e in evaluations) / num_questions
            avg_accuracy = sum(e.accuracy_score for e in evaluations) / num_questions
            avg_completeness = sum(e.completeness_score for e in evaluations) / num_questions
            avg_relevance = sum(e.relevance_score for e in evaluations) / num_questions

            # Calculate hallucination rate
            hallucination_count = sum(1 for e in evaluations if e.hallucination_detected)
            hallucination_rate = (hallucination_count / num_questions) * 100

            # Calculate response time and token averages
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            total_tokens = sum(tokens_used)

            # Calculate error rate
            error_rate = (errors / num_questions) * 100 if num_questions > 0 else 0

            aggregate_metrics[mode] = AggregateMetrics(
                mode=mode,
                num_questions=num_questions,
                avg_overall_score=avg_overall,
                avg_accuracy_score=avg_accuracy,
                avg_completeness_score=avg_completeness,
                avg_relevance_score=avg_relevance,
                hallucination_rate=hallucination_rate,
                avg_response_time_ms=avg_response_time,
                total_tokens_used=total_tokens,
                error_rate=error_rate,
            )

        return aggregate_metrics

    def compare_modes(
        self,
        evaluation_run: EvaluationRun,
    ) -> Dict[str, Any]:
        """
        Generate a detailed comparison between RAG modes.

        Args:
            evaluation_run: Completed evaluation run

        Returns:
            Dictionary with comparative analysis
        """
        comparison = {
            "summary": {},
            "hallucination_analysis": {},
            "performance_by_difficulty": {},
            "performance_by_question_type": {},
        }

        # Overall summary comparison
        for mode in RAGMode:
            if mode in evaluation_run.aggregate_metrics:
                metrics = evaluation_run.aggregate_metrics[mode]
                comparison["summary"][mode.value] = {
                    "avg_overall_score": metrics.avg_overall_score,
                    "avg_accuracy_score": metrics.avg_accuracy_score,
                    "hallucination_rate": metrics.hallucination_rate,
                    "avg_response_time_ms": metrics.avg_response_time_ms,
                    "error_rate": metrics.error_rate,
                }

        # Hallucination analysis
        baseline_hallucinations = 0
        fast_rag_hallucinations = 0
        agentic_rag_hallucinations = 0

        for qr in evaluation_run.question_results:
            if RAGMode.LLM_DIRECT in qr.evaluations:
                if qr.evaluations[RAGMode.LLM_DIRECT].hallucination_detected:
                    baseline_hallucinations += 1
            if RAGMode.FAST_RAG in qr.evaluations:
                if qr.evaluations[RAGMode.FAST_RAG].hallucination_detected:
                    fast_rag_hallucinations += 1
            if RAGMode.AGENTIC_RAG in qr.evaluations:
                if qr.evaluations[RAGMode.AGENTIC_RAG].hallucination_detected:
                    agentic_rag_hallucinations += 1

        total = len(evaluation_run.question_results)
        comparison["hallucination_analysis"] = {
            "llm_direct_count": baseline_hallucinations,
            "fast_rag_count": fast_rag_hallucinations,
            "agentic_rag_count": agentic_rag_hallucinations,
            "llm_direct_rate": (baseline_hallucinations / total) * 100,
            "fast_rag_rate": (fast_rag_hallucinations / total) * 100,
            "agentic_rag_rate": (agentic_rag_hallucinations / total) * 100,
            "fast_rag_reduction": baseline_hallucinations - fast_rag_hallucinations,
            "agentic_rag_reduction": baseline_hallucinations - agentic_rag_hallucinations,
        }

        # Performance by difficulty
        difficulty_stats = {"easy": {}, "medium": {}, "hard": {}}
        for difficulty in difficulty_stats.keys():
            for mode in RAGMode:
                mode_evals = [
                    qr.evaluations[mode]
                    for qr in evaluation_run.question_results
                    if qr.qa_pair.difficulty == difficulty and mode in qr.evaluations
                ]
                if mode_evals:
                    avg_score = sum(e.overall_score for e in mode_evals) / len(mode_evals)
                    halluc_count = sum(1 for e in mode_evals if e.hallucination_detected)
                    difficulty_stats[difficulty][mode.value] = {
                        "avg_score": avg_score,
                        "hallucination_rate": (halluc_count / len(mode_evals)) * 100,
                        "count": len(mode_evals),
                    }
        comparison["performance_by_difficulty"] = difficulty_stats

        # Performance by question type
        type_stats = {}
        for qr in evaluation_run.question_results:
            q_type = qr.qa_pair.question_type
            if q_type not in type_stats:
                type_stats[q_type] = {}
            for mode in RAGMode:
                if mode not in type_stats[q_type]:
                    type_stats[q_type][mode.value] = {"scores": [], "hallucinations": 0}
                if mode in qr.evaluations:
                    type_stats[q_type][mode.value]["scores"].append(
                        qr.evaluations[mode].overall_score
                    )
                    if qr.evaluations[mode].hallucination_detected:
                        type_stats[q_type][mode.value]["hallucinations"] += 1

        # Calculate averages for question types
        for q_type in type_stats:
            for mode_value in type_stats[q_type]:
                scores = type_stats[q_type][mode_value]["scores"]
                if scores:
                    type_stats[q_type][mode_value]["avg_score"] = sum(scores) / len(scores)
                    type_stats[q_type][mode_value]["count"] = len(scores)
                del type_stats[q_type][mode_value]["scores"]

        comparison["performance_by_question_type"] = type_stats

        return comparison
