"""
Dataset generator for RAG evaluation.

Uses a SOTA model (qwen3.6-plus) to generate question-answer pairs
from the stored knowledge base (KnowledgePoint, KnowledgeSummary, etc.).
"""

import json
import logging
from typing import List, Dict, Any

from api.evaluate.models import QuestionAnswerPair
from api.llm_client import get_llm_client

logger = logging.getLogger('LectureMind')


# Prompt template for generating Q&A pairs from knowledge base
DATASET_GENERATION_PROMPT = """You are an expert educational content evaluator. Your task is to generate high-quality question-answer pairs based on the provided lecture knowledge base.

## Ground Truth Knowledge Base:

{ground_truth_content}

## Instructions:

Generate {num_questions} diverse question-answer pairs that:
1. Cover different cognitive levels (factual recall, conceptual understanding, procedural application)
2. Span various difficulty levels (easy, medium, hard)
3. Test deep comprehension, not just surface-level memorization
4. Are answerable SOLELY from the provided knowledge base

For each question:
- Ensure the answer is fully supported by the ground truth content
- Include the specific knowledge points that support the answer
- Vary question types: what, why, how, compare/contrast, analyze

## Output Format:

Return a JSON object with this exact structure:
{{
  "qa_pairs": [
    {{
      "question": "Clear, specific question text",
      "ground_truth_answer": "Comprehensive answer based only on the knowledge base",
      "question_type": "factual|conceptual|procedural",
      "difficulty": "easy|medium|hard",
      "source_knowledge_ids": ["id1", "id2"],
      "metadata": {{
        "topic": "Main topic covered",
        "reasoning_required": "Description of reasoning needed"
      }}
    }}
  ]
}}

Requirements:
- Generate exactly {num_questions} pairs
- Questions must be unambiguous and have clear correct answers
- Answers should be comprehensive (2-4 sentences) but grounded in the knowledge base
- Do not include any information not present in the ground truth"""


class DatasetGenerator:
    """
    Generates evaluation datasets using a SOTA model.

    Uses the stored knowledge base (KnowledgePoint, KnowledgeSummary, VideoSection)
    to create question-answer pairs for evaluation.
    """

    def __init__(self, sota_model: str = "qwen3.6-plus"):
        """
        Initialize the dataset generator.

        Args:
            sota_model: Model name to use for generation (should be high-quality)
        """
        self.sota_model = sota_model
        self.llm = get_llm_client(model=sota_model)

    def generate_dataset(
        self,
        video_id: str,
        num_questions: int = 20,
        include_irrelevant: bool = True,
        irrelevant_ratio: float = 0.3,
    ) -> List[QuestionAnswerPair]:
        """
        Generate a dataset of question-answer pairs for a video.

        Args:
            video_id: UUID of the video to generate questions for
            num_questions: Number of Q&A pairs to generate (default 20)
            include_irrelevant: Whether to include questions not answerable from KB (for hallucination detection)
            irrelevant_ratio: Ratio of irrelevant questions (default 0.3 = 30%)

        Returns:
            List of QuestionAnswerPair objects
        """
        logger.info(f"Generating dataset for video {video_id} using {self.sota_model}")

        # Gather ground truth content from knowledge base
        ground_truth = self._gather_ground_truth(video_id)

        if not ground_truth:
            logger.warning(f"No ground truth content found for video {video_id}")
            return []

        # Format ground truth for the prompt
        ground_truth_text = self._format_ground_truth(ground_truth)

        # Calculate question distribution
        if include_irrelevant and num_questions >= 5:
            num_relevant = int(num_questions * (1 - irrelevant_ratio))
            num_irrelevant = num_questions - num_relevant
        else:
            num_relevant = num_questions
            num_irrelevant = 0

        logger.info(f"Generating {num_relevant} relevant + {num_irrelevant} irrelevant questions")

        qa_pairs = []

        # Generate relevant questions
        if num_relevant > 0:
            relevant_pairs = self._generate_relevant_questions(
                video_id, ground_truth_text, num_relevant
            )
            qa_pairs.extend(relevant_pairs)

        # Generate irrelevant questions (for hallucination detection)
        if num_irrelevant > 0:
            irrelevant_pairs = self._generate_irrelevant_questions(
                video_id, ground_truth_text, num_irrelevant
            )
            qa_pairs.extend(irrelevant_pairs)

        logger.info(f"Generated {len(qa_pairs)} Q&A pairs ({num_relevant} relevant, {num_irrelevant} irrelevant) for video {video_id}")
        return qa_pairs

    def _generate_relevant_questions(
        self, video_id: str, ground_truth_text: str, num_questions: int
    ) -> List[QuestionAnswerPair]:
        """Generate questions that are answerable from the knowledge base."""
        prompt = DATASET_GENERATION_PROMPT.format(
            ground_truth_content=ground_truth_text,
            num_questions=num_questions,
        )

        try:
            response = self.llm.chat(
                prompt=prompt,
                system_prompt="You are an expert at creating educational assessment questions. Always return valid JSON.",
                temperature=0.7,
                max_tokens=4096,
            )

            qa_data = self._parse_json_response(response)

            if not qa_data or "qa_pairs" not in qa_data:
                logger.error("Failed to generate valid Q&A pairs from model response")
                return []

            qa_pairs = []
            for item in qa_data["qa_pairs"]:
                qa_pair = QuestionAnswerPair(
                    question=item.get("question", ""),
                    ground_truth_answer=item.get("ground_truth_answer", ""),
                    question_type=item.get("question_type", "factual"),
                    difficulty=item.get("difficulty", "medium"),
                    source_knowledge_ids=item.get("source_knowledge_ids", []),
                    metadata={**item.get("metadata", {}), "is_relevant": True},
                )
                qa_pairs.append(qa_pair)

            return qa_pairs

        except Exception as e:
            logger.exception(f"Error generating relevant questions: {e}")
            return []

    def _generate_irrelevant_questions(
        self, video_id: str, ground_truth_text: str, num_questions: int
    ) -> List[QuestionAnswerPair]:
        """Generate questions that are NOT answerable from the knowledge base (for hallucination detection)."""
        IRRELEVANT_QUESTION_PROMPT = """You are an expert at creating evaluation questions for RAG systems.
Your task is to generate questions that appear related to the lecture topic but CANNOT be answered from the provided knowledge base.
These questions will be used to test whether AI systems hallucinate answers when they don't have sufficient information.

## Ground Truth Knowledge Base:

{ground_truth_content}

## Instructions:

Generate {num_questions} questions that:
1. Sound like they could be about the lecture topic (plausible questions a student might ask)
2. Are NOT answerable from the provided knowledge base (information is missing or not covered)
3. Test whether AI systems will hallucinate/fabricate answers when they lack information
4. Include a mix of: specific details not in KB, related but external topics, and questions requiring info from outside sources

For each question, the ground_truth_answer should clearly state that the information is NOT available in the knowledge base.

## Output Format:

Return a JSON object with this exact structure:
{{
  "qa_pairs": [
    {{
      "question": "Question that cannot be answered from KB",
      "ground_truth_answer": "INSUFFICIENT_INFO: The knowledge base does not contain information about [specific topic].",
      "question_type": "irrelevant",
      "difficulty": "medium",
      "source_knowledge_ids": [],
      "metadata": {{
        "topic": "Topic the question appears to be about",
        "reasoning_required": "Why this question cannot be answered from KB",
        "is_relevant": false,
        "is_hallucination_test": true
      }}
    }}
  ]
}}

Requirements:
- Questions should be plausible and related to the general domain
- Answers must honestly state that information is not available
- Do NOT include any information not present in the ground truth"""

        prompt = IRRELEVANT_QUESTION_PROMPT.format(
            ground_truth_content=ground_truth_text[:8000],  # Limit context
            num_questions=num_questions,
        )

        try:
            response = self.llm.chat(
                prompt=prompt,
                system_prompt="You are an expert at creating adversarial test questions for RAG evaluation. Generate questions that test hallucination detection.",
                temperature=0.8,  # Higher temperature for more diverse questions
                max_tokens=4096,
            )

            qa_data = self._parse_json_response(response)

            if not qa_data or "qa_pairs" not in qa_data:
                logger.error("Failed to generate valid irrelevant Q&A pairs from model response")
                return []

            qa_pairs = []
            for item in qa_data["qa_pairs"]:
                qa_pair = QuestionAnswerPair(
                    question=item.get("question", ""),
                    ground_truth_answer=item.get("ground_truth_answer", "INSUFFICIENT_INFO: Not available in knowledge base."),
                    question_type="irrelevant",
                    difficulty="medium",
                    source_knowledge_ids=[],
                    metadata={
                        **item.get("metadata", {}),
                        "is_relevant": False,
                        "is_hallucination_test": True,
                    },
                )
                qa_pairs.append(qa_pair)

            logger.info(f"Generated {len(qa_pairs)} irrelevant questions for hallucination detection")
            return qa_pairs

        except Exception as e:
            logger.exception(f"Error generating irrelevant questions: {e}")
            return []

    def _gather_ground_truth(self, video_id: str) -> Dict[str, Any]:
        """
        Gather all ground truth content from the knowledge base for a video.

        Args:
            video_id: UUID of the video

        Returns:
            Dictionary containing knowledge summary, points, and sections
        """
        from api.models import (
            Video, KnowledgeSummary, KnowledgePoint, VideoSection
        )

        ground_truth = {
            "video": None,
            "summary": None,
            "knowledge_points": [],
            "sections": [],
        }

        try:
            # Get video info
            video = Video.objects.get(id=video_id)
            ground_truth["video"] = {
                "id": str(video.id),
                "title": video.title,
                "duration": video.duration,
            }

            # Get knowledge summary
            try:
                summary = KnowledgeSummary.objects.get(video_id=video_id)
                ground_truth["summary"] = {
                    "overview": summary.overview,
                    "key_topics": summary.key_topics,
                    "learning_objectives": summary.learning_objectives,
                    "prerequisites": summary.prerequisites,
                    "difficulty_level": summary.difficulty_level,
                }
            except KnowledgeSummary.DoesNotExist:
                logger.warning(f"No knowledge summary found for video {video_id}")

            # Get knowledge points
            knowledge_points = KnowledgePoint.objects.filter(video_id=video_id).select_related('section')
            for kp in knowledge_points:
                ground_truth["knowledge_points"].append({
                    "id": str(kp.id),
                    "title": kp.title,
                    "summary": kp.summary,
                    "key_terms": kp.key_terms,
                    "importance": kp.importance,
                    "section_order": kp.section.order if kp.section else 0,
                })

            # Get video sections
            sections = VideoSection.objects.filter(video_id=video_id)
            for section in sections:
                ground_truth["sections"].append({
                    "id": str(section.id),
                    "title": section.title,
                    "order": section.order,
                    "begin_time": section.begin_time,
                    "end_time": section.end_time,
                    "transcript_text": section.transcript_text[:1000] if section.transcript_text else "",
                })

        except Video.DoesNotExist:
            logger.error(f"Video {video_id} not found")
        except Exception as e:
            logger.exception(f"Error gathering ground truth: {e}")

        return ground_truth

    def _format_ground_truth(self, ground_truth: Dict[str, Any]) -> str:
        """
        Format ground truth content for the prompt.

        Args:
            ground_truth: Dictionary containing knowledge base content

        Returns:
            Formatted string for the prompt
        """
        lines = []

        # Video info
        if ground_truth.get("video"):
            video = ground_truth["video"]
            lines.append(f"# Video: {video['title']}")
            lines.append(f"Duration: {video['duration']:.0f} seconds")
            lines.append("")

        # Knowledge Summary
        if ground_truth.get("summary"):
            summary = ground_truth["summary"]
            lines.append("## Lecture Summary")
            lines.append(summary.get("overview", ""))
            lines.append("")
            if summary.get("key_topics"):
                lines.append(f"Key Topics: {', '.join(summary['key_topics'])}")
            if summary.get("learning_objectives"):
                lines.append(f"Learning Objectives: {', '.join(summary['learning_objectives'])}")
            lines.append("")

        # Knowledge Points
        if ground_truth.get("knowledge_points"):
            lines.append("## Knowledge Points")
            for kp in ground_truth["knowledge_points"]:
                lines.append(f"\n### {kp['title']} (Importance: {kp['importance']:.2f})")
                lines.append(kp.get("summary", ""))
                if kp.get("key_terms"):
                    lines.append(f"Key Terms: {', '.join(kp['key_terms'])}")
            lines.append("")

        # Sections
        if ground_truth.get("sections"):
            lines.append("## Video Sections")
            for section in ground_truth["sections"]:
                lines.append(f"\n### Section {section['order']}: {section['title']}")
                lines.append(f"Time: {section['begin_time']:.0f}s - {section['end_time']:.0f}s")
                if section.get("transcript_text"):
                    lines.append(f"Content: {section['transcript_text'][:500]}...")
            lines.append("")

        return "\n".join(lines)

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """
        Parse JSON from model response, handling various formats.

        Args:
            response: Raw model response string

        Returns:
            Parsed JSON dictionary
        """
        # Try direct JSON parsing first
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        import re

        # Look for JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Look for JSON object anywhere in the response
        json_match = re.search(r'(\{[\s\S]*"qa_pairs"[\s\S]*\})', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse JSON from response: {response[:500]}")
        return {}
