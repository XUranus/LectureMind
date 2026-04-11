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
    Fast RAG mode - standard retrieval-augmented generation.

    Uses the existing RAGEngine to retrieve relevant context
    and generate an answer based on that context.
    """

    @property
    def mode(self) -> RAGMode:
        return RAGMode.FAST_RAG

    def answer(self, question: str) -> ModeResponse:
        """Answer question using RAG with vector retrieval."""
        from api.rag_engine import RAGEngine

        start_time = time.time()

        try:
            # Use the existing RAGEngine
            engine = RAGEngine(video_id=self.video_id, top_k=6)
            answer, citations = engine.ask(question)

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
        """Rough token estimation."""
        return len(text) // 4


class AgenticRAGMode(BaseRAGMode):
    """
    Agentic RAG mode - multi-step reasoning with tool use.

    Uses the existing AgentRunner to perform multi-step retrieval
    and reasoning before answering.
    """

    @property
    def mode(self) -> RAGMode:
        return RAGMode.AGENTIC_RAG

    def answer(self, question: str) -> ModeResponse:
        """Answer question using agentic multi-step reasoning."""
        from api.agent_graph import run_agent

        start_time = time.time()

        try:
            # Use the existing agent runner
            answer, tool_steps, citations = run_agent(
                video_id=self.video_id,
                question=question,
                chat_history=None,
            )

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
