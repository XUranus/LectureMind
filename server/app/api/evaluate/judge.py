"""
Judge system for evaluating RAG responses.

Uses a SOTA model (qwen3.6-plus) to evaluate and score responses
from different RAG modes against ground truth answers.
"""

import json
import logging
from typing import Dict, Any

from api.evaluate.models import RAGMode, JudgeEvaluation, QuestionAnswerPair, ModeResponse
from api.llm_client import get_llm_client

logger = logging.getLogger('LectureMind')


# Prompt template for the judge model
JUDGE_PROMPT_TEMPLATE = """You are an expert evaluator assessing the quality of AI-generated answers to lecture-related questions. Your task is to evaluate the response based on accuracy, completeness, and hallucination.

## Evaluation Criteria:

1. **Accuracy (0-100)**: How factually correct is the answer compared to the ground truth?
   - 100: Perfectly accurate, all facts match ground truth
   - 80-99: Minor inaccuracies or omissions
   - 60-79: Some correct information but notable errors
   - 40-59: Mixed accuracy, significant errors present
   - 20-39: Mostly incorrect with some correct elements
   - 0-19: Completely wrong or irrelevant

2. **Completeness (0-100)**: How thoroughly does the answer address the question?
   - 100: Fully comprehensive, covers all aspects
   - 80-99: Good coverage with minor gaps
   - 60-79: Adequate but missing some important points
   - 40-59: Partial coverage, significant gaps
   - 20-39: Very incomplete
   - 0-19: Does not address the question

3. **Hallucination Detection**: Does the answer contain fabricated information not supported by the ground truth?
   - Check for: made-up facts, incorrect citations, invented statistics, fabricated timestamps
   - DO NOT flag as hallucination: General knowledge answers when lecture content is insufficient
   - DO NOT flag as hallucination: Fallback responses that explicitly state they're using general knowledge
   - DO flag as hallucination: Specific lecture citations (timestamps, section names) that don't exist in ground truth
   - SPECIAL CASE: If ground truth starts with "INSUFFICIENT_INFO", the question is NOT answerable from KB. If the model provides a specific answer instead of admitting it doesn't know, FLAG THIS AS HALLUCINATION.

4. **Relevance (0-100)**: How relevant is the answer to the specific question asked?

5. **Overall Score (0-100)**: Weighted combination considering all factors

## Input Data:

### Question:
{question}

### Ground Truth Answer (Correct Answer):
{ground_truth}

### Model Response to Evaluate:
{model_response}

### RAG Mode:
{rag_mode}

## Instructions:

Evaluate the model response and provide:
1. Numerical scores for each criterion
2. Boolean flag for hallucination detection
3. Detailed explanation of your evaluation
4. Specific comparison to ground truth highlighting differences

## Output Format:

Return ONLY a JSON object with this exact structure:
{{
  "overall_score": 85,
  "accuracy_score": 90,
  "completeness_score": 80,
  "relevance_score": 95,
  "hallucination_detected": false,
  "hallucination_details": "If hallucination detected, describe what was fabricated. Otherwise empty string.",
  "explanation": "Detailed explanation of the evaluation, strengths and weaknesses of the response",
  "comparison_to_ground_truth": "Specific comparison highlighting where the response matches or diverges from ground truth"
}}

Requirements:
- Be objective and consistent in your evaluation
- Focus on factual correctness relative to ground truth
- Only flag hallucinations for fabricated lecture-specific details (timestamps, section names, examples)
- Do NOT penalize fallback responses that honestly use general knowledge when lecture content is insufficient
- Consider the RAG mode context (LLM Direct has no lecture context, Fast RAG has retrieved context, Agentic RAG has multi-step reasoning)"""


class JudgeSystem:
    """
    Judge system for evaluating RAG responses using a SOTA model.

    Compares model responses against ground truth and provides
    quantitative scores and qualitative analysis.
    """

    def __init__(self, sota_model: str = "qwen3.6-plus"):
        """
        Initialize the judge system.

        Args:
            sota_model: High-quality model to use for evaluation
        """
        self.sota_model = sota_model
        self.llm = get_llm_client(model=sota_model)

    def evaluate_response(
        self,
        qa_pair: QuestionAnswerPair,
        mode_response: ModeResponse,
    ) -> JudgeEvaluation:
        """
        Evaluate a single response from a RAG mode.

        Args:
            qa_pair: The question-answer pair with ground truth
            mode_response: The response from the RAG mode to evaluate

        Returns:
            JudgeEvaluation with scores and analysis
        """
        # If there was an error in the mode response, return a failed evaluation
        if mode_response.error and not mode_response.answer:
            return JudgeEvaluation(
                mode=mode_response.mode,
                overall_score=0.0,
                accuracy_score=0.0,
                completeness_score=0.0,
                hallucination_detected=False,
                hallucination_details=f"Error in response: {mode_response.error}",
                relevance_score=0.0,
                explanation="Evaluation failed due to error in mode response",
                comparison_to_ground_truth="N/A - Error occurred",
            )

        # Clean the answer by removing fallback indicators for fair evaluation
        cleaned_answer = self._clean_answer_for_evaluation(mode_response.answer)

        # Build the judge prompt
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            question=qa_pair.question,
            ground_truth=qa_pair.ground_truth_answer,
            model_response=cleaned_answer,
            rag_mode=mode_response.mode.value,
        )

        try:
            # Call the judge model
            response = self.llm.chat(
                prompt=prompt,
                system_prompt="You are an objective evaluator. Always return valid JSON with numerical scores.",
                temperature=0.3,  # Lower temperature for consistent evaluation
                max_tokens=2048,
            )

            # Parse the evaluation result
            eval_data = self._parse_evaluation_response(response)

            return JudgeEvaluation(
                mode=mode_response.mode,
                overall_score=eval_data.get("overall_score", 0.0),
                accuracy_score=eval_data.get("accuracy_score", 0.0),
                completeness_score=eval_data.get("completeness_score", 0.0),
                hallucination_detected=eval_data.get("hallucination_detected", False),
                hallucination_details=eval_data.get("hallucination_details", ""),
                relevance_score=eval_data.get("relevance_score", 0.0),
                explanation=eval_data.get("explanation", ""),
                comparison_to_ground_truth=eval_data.get("comparison_to_ground_truth", ""),
            )

        except Exception as e:
            logger.exception(f"Judge evaluation failed: {e}")
            return JudgeEvaluation(
                mode=mode_response.mode,
                overall_score=0.0,
                accuracy_score=0.0,
                completeness_score=0.0,
                hallucination_detected=False,
                hallucination_details=f"Judge evaluation error: {str(e)}",
                relevance_score=0.0,
                explanation="Evaluation failed due to judge system error",
                comparison_to_ground_truth="N/A",
            )

    def evaluate_all_modes(
        self,
        qa_pair: QuestionAnswerPair,
        responses: Dict[RAGMode, ModeResponse],
    ) -> Dict[RAGMode, JudgeEvaluation]:
        """
        Evaluate responses from all RAG modes for a single question.

        Args:
            qa_pair: The question-answer pair with ground truth
            responses: Dictionary mapping RAG modes to their responses

        Returns:
            Dictionary mapping RAG modes to their evaluations
        """
        evaluations = {}

        for mode, response in responses.items():
            logger.debug(f"Evaluating {mode.value} response for question: {qa_pair.question[:50]}...")
            evaluation = self.evaluate_response(qa_pair, response)
            evaluations[mode] = evaluation

        return evaluations

    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the JSON evaluation response from the judge model.

        Args:
            response: Raw response string from judge

        Returns:
            Dictionary with evaluation scores
        """
        # Try direct JSON parsing
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        import re

        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Look for JSON object anywhere
        json_match = re.search(r'(\{[\s\S]*"overall_score"[\s\S]*\})', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse judge evaluation: {response[:500]}")

        # Return default values if parsing fails
        return {
            "overall_score": 0.0,
            "accuracy_score": 0.0,
            "completeness_score": 0.0,
            "relevance_score": 0.0,
            "hallucination_detected": False,
            "hallucination_details": "Failed to parse judge response",
            "explanation": "Parsing error",
            "comparison_to_ground_truth": "Parsing error",
        }

    def _clean_answer_for_evaluation(self, answer: str) -> str:
        """
        Remove fallback indicators and metadata from answer before evaluation.
        This ensures fair evaluation of the actual content.
        """
        import re

        if not answer:
            return answer

        # Remove fallback indicators
        fallback_patterns = [
            r'\[Retrieval fallback:.*?\]\n*',
            r'\[Agent fallback:.*?\]\n*',
        ]

        cleaned = answer
        for pattern in fallback_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        return cleaned.strip()


class ComparativeAnalyzer:
    """
    Analyzes and compares evaluations across different RAG modes.

    Provides insights into relative performance and hallucination reduction.
    """

    def __init__(self):
        pass

    def analyze_comparison(
        self,
        evaluations: Dict[RAGMode, JudgeEvaluation],
    ) -> Dict[str, Any]:
        """
        Analyze comparative performance across RAG modes.

        Args:
            evaluations: Dictionary of evaluations by mode

        Returns:
            Dictionary with comparative analysis
        """
        analysis = {
            "best_overall": None,
            "best_accuracy": None,
            "least_hallucination": None,
            "hallucination_reduction": {},
            "score_improvements": {},
        }

        # Find best performing modes
        if evaluations:
            # Best overall score
            best_overall = max(
                evaluations.items(),
                key=lambda x: x[1].overall_score
            )
            analysis["best_overall"] = {
                "mode": best_overall[0].value,
                "score": best_overall[1].overall_score,
            }

            # Best accuracy
            best_accuracy = max(
                evaluations.items(),
                key=lambda x: x[1].accuracy_score
            )
            analysis["best_accuracy"] = {
                "mode": best_accuracy[0].value,
                "score": best_accuracy[1].accuracy_score,
            }

            # Least hallucination
            modes_with_hallucination = [
                (mode, eval.hallucination_detected)
                for mode, eval in evaluations.items()
            ]
            non_hallucinating = [
                mode for mode, detected in modes_with_hallucination
                if not detected
            ]
            if non_hallucinating:
                analysis["least_hallucination"] = [m.value for m in non_hallucinating]
            else:
                analysis["least_hallucination"] = []

            # Calculate improvements over LLM Direct baseline
            if RAGMode.LLM_DIRECT in evaluations:
                baseline = evaluations[RAGMode.LLM_DIRECT]
                for mode in [RAGMode.FAST_RAG, RAGMode.AGENTIC_RAG]:
                    if mode in evaluations:
                        mode_eval = evaluations[mode]
                        analysis["score_improvements"][mode.value] = {
                            "overall": mode_eval.overall_score - baseline.overall_score,
                            "accuracy": mode_eval.accuracy_score - baseline.accuracy_score,
                            "completeness": mode_eval.completeness_score - baseline.completeness_score,
                        }

                        # Hallucination reduction
                        if baseline.hallucination_detected and not mode_eval.hallucination_detected:
                            analysis["hallucination_reduction"][mode.value] = True

        return analysis
