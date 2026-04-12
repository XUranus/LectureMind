"""
RAG mode implementations for evaluation.

Implements three modes for comparison:
1. LLM Direct: Direct LLM response without any retrieval
2. Fast RAG: Standard retrieval-augmented generation
3. Agentic RAG: Multi-step agent with tool use
"""

import time
import logging
from typing import Dict, Any, List, Tuple
from abc import ABC, abstractmethod

from api.evaluate.models import RAGMode, ModeResponse
from api.llm_client import get_llm_client

logger = logging.getLogger('LectureMind')


class BaseRAGMode(ABC):
    """Abstract base class for RAG modes."""

    def __init__(self, video_id: str, model: str):
        self.video_id = video_id
        self.model = model
        self.llm = get_llm_client(model=model)

    @property
    @abstractmethod
    def mode(self) -> RAGMode:
        """Return the RAG mode type."""
        pass

    @abstractmethod
    def answer(self, question: str) -> ModeResponse:
        """
        Answer a question using this RAG mode.

        Args:
            question: The question to answer

        Returns:
            ModeResponse containing the answer and metadata
        """
        pass


class LLMDirectMode(BaseRAGMode):
    """
    LLM Direct mode - answers without any retrieval context.

    This serves as a baseline to show the impact of hallucination
    when the model has no access to the knowledge base.
    """

    SYSTEM_PROMPT = """You are a helpful assistant answering questions about a lecture video.

Important: Answer based on your general knowledge. You do NOT have access to the lecture content, so if you're unsure about specific details from the lecture, acknowledge that limitation.

Be honest if you don't know something specific to the lecture."""

    @property
    def mode(self) -> RAGMode:
        return RAGMode.LLM_DIRECT

    def answer(self, question: str) -> ModeResponse:
        """Answer question using only the LLM's parametric knowledge."""
        start_time = time.time()

        try:
            response = self.llm.chat(
                prompt=question,
                system_prompt=self.SYSTEM_PROMPT,
                temperature=0.5,
                max_tokens=2048,
            )

            response_time_ms = (time.time() - start_time) * 1000

            return ModeResponse(
                mode=self.mode,
                answer=response,
                response_time_ms=response_time_ms,
                tokens_used=self._estimate_tokens(question + response),
                citations=[],
                tool_calls=[],
                error=None,
            )

        except Exception as e:
            logger.error(f"LLM Direct mode failed: {e}")
            return ModeResponse(
                mode=self.mode,
                answer="",
                response_time_ms=(time.time() - start_time) * 1000,
                tokens_used=0,
                citations=[],
                tool_calls=[],
                error=str(e),
            )

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (approx 4 chars per token)."""
        return len(text) // 4


class FastRAGMode(BaseRAGMode):
    """
    Fast RAG mode - standard retrieval-augmented generation with fallback.

    Uses the existing RAGEngine to retrieve relevant context
    and generate an answer based on that context.
    Includes fallback to LLM direct when retrieval fails.
    """

    # Minimum relevance threshold for retrieved documents
    MIN_RELEVANCE_THRESHOLD = 0.3
    # Minimum number of relevant documents required
    MIN_DOCUMENTS_REQUIRED = 2

    @property
    def mode(self) -> RAGMode:
        return RAGMode.FAST_RAG

    def answer(self, question: str) -> ModeResponse:
        """Answer question using RAG with vector retrieval and fallback."""
        from api.rag_engine import RAGEngine
        from api.vector_store import get_vector_store

        start_time = time.time()

        try:
            # First, check if we have relevant context
            store = get_vector_store()
            retrieval_results = store.query(
                query_text=question,
                video_id=self.video_id,
                top_k=8
            )

            # Filter for high-quality results
            relevant_results = [
                r for r in retrieval_results
                if r.get("relevance", 0) >= self.MIN_RELEVANCE_THRESHOLD
            ]

            # If insufficient relevant context, fall back to LLM direct
            if len(relevant_results) < self.MIN_DOCUMENTS_REQUIRED:
                logger.warning(
                    f"Fast RAG: Insufficient relevant context "
                    f"({len(relevant_results)} docs, need {self.MIN_DOCUMENTS_REQUIRED}). "
                    f"Falling back to LLM direct."
                )
                return self._fallback_to_llm(question, start_time)

            # Use the existing RAGEngine with verified context
            engine = RAGEngine(video_id=self.video_id, top_k=6)
            answer, citations = engine.ask(question)

            # Check if answer is empty or too short (indicates generation failure)
            if not answer or len(answer.strip()) < 50:
                logger.warning(
                    f"Fast RAG: Empty or short answer ({len(answer) if answer else 0} chars). "
                    f"Falling back to LLM direct."
                )
                return self._fallback_to_llm(question, start_time)

            response_time_ms = (time.time() - start_time) * 1000

            # Format citations for response
            formatted_citations = [
                {
                    "source_num": c.get("source_num", i + 1),
                    "title": c.get("title", ""),
                    "begin_time": c.get("begin_time", 0),
                    "end_time": c.get("end_time", 0),
                    "type": c.get("type", "unknown"),
                    "relevance": c.get("relevance", 0),
                }
                for i, c in enumerate(citations)
            ]

            return ModeResponse(
                mode=self.mode,
                answer=answer,
                response_time_ms=response_time_ms,
                tokens_used=self._estimate_tokens(question + answer),
                citations=formatted_citations,
                tool_calls=[],
                error=None,
            )

        except Exception as e:
            logger.error(f"Fast RAG mode failed: {e}")
            # Fallback to LLM direct on any error
            return self._fallback_to_llm(question, start_time, error=str(e))

    def _fallback_to_llm(
        self, question: str, start_time: float, error: str = None
    ) -> ModeResponse:
        """Fallback to LLM direct when RAG fails."""
        try:
            system_prompt = """You are a helpful assistant answering questions.

The lecture knowledge base does not contain specific information about this question, so answer based on your general knowledge. Be honest about limitations."""

            response = self.llm.chat(
                prompt=question,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=2048,
            )

            response_time_ms = (time.time() - start_time) * 1000

            # Add fallback note to answer
            answer = f"[Retrieval fallback: Using general knowledge]\n\n{response}"

            return ModeResponse(
                mode=self.mode,
                answer=answer,
                response_time_ms=response_time_ms,
                tokens_used=self._estimate_tokens(question + answer),
                citations=[],
                tool_calls=[],
                error=error,  # Preserve original error for logging
            )

        except Exception as fallback_error:
            logger.error(f"Fast RAG fallback also failed: {fallback_error}")
            return ModeResponse(
                mode=self.mode,
                answer="",
                response_time_ms=(time.time() - start_time) * 1000,
                tokens_used=0,
                citations=[],
                tool_calls=[],
                error=f"RAG failed: {error}; Fallback failed: {fallback_error}",
            )

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation."""
        return len(text) // 4


class AgenticRAGMode(BaseRAGMode):
    """
    Agentic RAG mode - multi-step reasoning with tool use and fallback.

    Uses the existing AgentRunner to perform multi-step retrieval
    and reasoning before answering. Includes fallback to Fast RAG
    when agent fails or produces insufficient results.
    """

    # Minimum tool calls to consider agentic search successful
    MIN_TOOL_CALLS = 1
    # Minimum answer length to consider response valid
    MIN_ANSWER_LENGTH = 50

    @property
    def mode(self) -> RAGMode:
        return RAGMode.AGENTIC_RAG

    def answer(self, question: str) -> ModeResponse:
        """Answer question using agentic multi-step reasoning with fallback."""
        from api.agent_graph import run_agent
        from api.vector_store import get_vector_store

        start_time = time.time()

        try:
            # Check if we have any relevant content first
            store = get_vector_store()
            retrieval_results = store.query(
                query_text=question,
                video_id=self.video_id,
                top_k=5
            )

            # Filter for relevant results
            relevant_results = [
                r for r in retrieval_results
                if r.get("relevance", 0) >= 0.3
            ]

            # If no relevant content, skip agent and fallback immediately
            if not relevant_results:
                logger.warning(
                    "Agentic RAG: No relevant content found. Falling back to LLM direct."
                )
                return self._fallback_to_llm(question, start_time)

            # Use the existing agent runner
            answer, tool_steps, citations = run_agent(
                video_id=self.video_id,
                question=question,
                chat_history=None,
            )

            # Check if agent produced valid results
            if len(tool_steps) < self.MIN_TOOL_CALLS:
                logger.warning(
                    f"Agentic RAG: Insufficient tool calls ({len(tool_steps)}). "
                    f"Falling back to Fast RAG."
                )
                return self._fallback_to_fast_rag(question, start_time)

            if not answer or len(answer.strip()) < self.MIN_ANSWER_LENGTH:
                logger.warning(
                    f"Agentic RAG: Answer too short ({len(answer) if answer else 0} chars). "
                    f"Falling back to Fast RAG."
                )
                return self._fallback_to_fast_rag(question, start_time)

            response_time_ms = (time.time() - start_time) * 1000

            # Format tool calls for response
            formatted_tool_calls = [
                {
                    "tool": step.get("tool", ""),
                    "args": step.get("args", {}),
                    "result_preview": step.get("result", "")[:200],
                }
                for step in tool_steps
            ]

            # Format citations
            formatted_citations = [
                {
                    "source_num": c.get("source_num", i + 1),
                    "title": c.get("title", ""),
                    "begin_time": c.get("begin_time", 0),
                    "end_time": c.get("end_time", 0),
                    "type": c.get("type", "unknown"),
                    "relevance": c.get("relevance", 0),
                }
                for i, c in enumerate(citations)
            ]

            return ModeResponse(
                mode=self.mode,
                answer=answer,
                response_time_ms=response_time_ms,
                tokens_used=self._estimate_tokens(question + answer),
                citations=formatted_citations,
                tool_calls=formatted_tool_calls,
                error=None,
                metadata={"num_tool_calls": len(tool_steps)},
            )

        except Exception as e:
            logger.error(f"Agentic RAG mode failed: {e}")
            return self._fallback_to_fast_rag(question, start_time, error=str(e))

    def _fallback_to_fast_rag(
        self, question: str, start_time: float, error: str = None
    ) -> ModeResponse:
        """Fallback to Fast RAG when agentic fails."""
        logger.info("Agentic RAG: Falling back to Fast RAG mode")
        fast_mode = FastRAGMode(self.video_id, self.model)
        response = fast_mode.answer(question)
        # Update mode to indicate fallback
        response.mode = self.mode
        response.error = error
        return response

    def _fallback_to_llm(
        self, question: str, start_time: float, error: str = None
    ) -> ModeResponse:
        """Fallback to LLM direct when no relevant content."""
        try:
            system_prompt = """You are a helpful assistant answering questions.

The lecture knowledge base does not contain specific information about this question, so answer based on your general knowledge. Be honest about limitations."""

            response = self.llm.chat(
                prompt=question,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=2048,
            )

            response_time_ms = (time.time() - start_time) * 1000

            answer = f"[Agent fallback: No relevant lecture content found]\n\n{response}"

            return ModeResponse(
                mode=self.mode,
                answer=answer,
                response_time_ms=response_time_ms,
                tokens_used=self._estimate_tokens(question + answer),
                citations=[],
                tool_calls=[],
                error=error,
            )

        except Exception as fallback_error:
            logger.error(f"Agentic RAG fallback also failed: {fallback_error}")
            return ModeResponse(
                mode=self.mode,
                answer="",
                response_time_ms=(time.time() - start_time) * 1000,
                tokens_used=0,
                citations=[],
                tool_calls=[],
                error=f"Agent failed: {error}; Fallback failed: {fallback_error}",
            )

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation."""
        return len(text) // 4


class RAGModeFactory:
    """Factory for creating RAG mode instances."""

    @staticmethod
    def create_mode(mode: RAGMode, video_id: str, model: str) -> BaseRAGMode:
        """
        Create a RAG mode instance.

        Args:
            mode: The RAG mode to create
            video_id: Video UUID for context
            model: Model name to use for generation

        Returns:
            BaseRAGMode instance
        """
        mode_map = {
            RAGMode.LLM_DIRECT: LLMDirectMode,
            RAGMode.FAST_RAG: FastRAGMode,
            RAGMode.AGENTIC_RAG: AgenticRAGMode,
        }

        mode_class = mode_map.get(mode)
        if not mode_class:
            raise ValueError(f"Unknown RAG mode: {mode}")

        return mode_class(video_id, model)

    @staticmethod
    def get_all_modes(video_id: str, model: str) -> List[BaseRAGMode]:
        """
        Get all RAG mode instances for evaluation.

        Args:
            video_id: Video UUID for context
            model: Model name to use for generation

        Returns:
            List of all RAG mode instances
        """
        return [
            RAGModeFactory.create_mode(RAGMode.LLM_DIRECT, video_id, model),
            RAGModeFactory.create_mode(RAGMode.FAST_RAG, video_id, model),
            RAGModeFactory.create_mode(RAGMode.AGENTIC_RAG, video_id, model),
        ]
