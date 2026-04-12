"""
RAG (Retrieval-Augmented Generation) engine for lecture video Q&A.

Pipeline:
1. Retrieve relevant knowledge from ChromaDB vector store
2. Build context from retrieved documents + knowledge summary
3. Assemble prompt with citations metadata
4. Stream LLM response with inline source references

Usage:
    from api.rag_engine import RAGEngine

    engine = RAGEngine(video_id="uuid-str")
    # Non-streaming
    answer, citations = engine.ask("What is gradient descent?")
    # Streaming
    for chunk in engine.ask_stream("What is gradient descent?"):
        print(chunk, end="")
"""

import json
import logging
from typing import Dict, Any, List, Optional, Generator, Tuple

logger = logging.getLogger('LectureMind')


RAG_SYSTEM_PROMPT = """You are a knowledgeable teaching assistant for a video lecture. Answer the student's question based on the lecture content provided below.

Instructions:
- Answer ONLY based on the provided context. If the context doesn't contain enough information, clearly state: "The lecture content does not provide specific information about this topic."
- When referencing specific lecture content, cite the source using [Source N] notation matching the numbered sources below.
- Be concise but thorough. Use markdown formatting for clarity.
- If the question is about a specific concept, explain it as taught in this lecture.
- Maintain an educational, helpful tone.
- DO NOT make up information, examples, or timestamps that are not in the provided context."""

RAG_CONTEXT_TEMPLATE = """## Lecture Context

### Video: {video_title}

{summary_section}

### Retrieved Sources:
{sources_section}

---
Student Question: {question}"""


def _format_time(seconds: float) -> str:
    m, s = int(seconds // 60), int(seconds % 60)
    return f"{m:02d}:{s:02d}"


class RAGEngine:
    """
    Retrieval-Augmented Generation engine for lecture video Q&A.
    Combines vector search with LLM generation for grounded answers.
    """

    def __init__(self, video_id: str, top_k: int = 6):
        self.video_id = video_id
        self.top_k = top_k

    def _retrieve_context(self, query: str) -> Tuple[List[Dict[str, Any]], str]:
        """
        Retrieve relevant documents from vector store and format as context string.
        Implements adaptive retrieval with relevance filtering.

        Returns:
            (citations_list, formatted_sources_text)
        """
        from api.vector_store import get_vector_store

        store = get_vector_store()

        # Try with higher top_k first, then filter
        results = store.query(
            query_text=query,
            video_id=self.video_id,
            top_k=self.top_k * 2,  # Retrieve more to allow better filtering
        )

        citations = []
        sources_lines = []

        # Adaptive relevance threshold based on top result
        max_relevance = max([r.get("relevance", 0) for r in results]) if results else 0
        # Use dynamic threshold: at least 0.3 or 60% of max relevance
        relevance_threshold = max(0.3, max_relevance * 0.6)

        for i, result in enumerate(results):
            meta = result.get("metadata", {})
            source_num = i + 1

            title = meta.get("title", "Unknown")
            begin_time = float(meta.get("begin_time", 0))
            end_time = float(meta.get("end_time", 0))
            content_type = meta.get("type", "unknown")
            relevance = result.get("relevance", 0)

            # Only include high-quality relevant results
            if relevance < relevance_threshold:
                continue

            # Limit to top_k results after filtering
            if len(citations) >= self.top_k:
                break

            time_range = f"{_format_time(begin_time)} - {_format_time(end_time)}"
            text_preview = result.get("text", "")[:600]  # Slightly longer context

            sources_lines.append(
                f"[Source {source_num}] ({content_type}) \"{title}\" "
                f"[{time_range}] (relevance: {relevance:.2f})\n"
                f"{text_preview}"
            )

            citations.append({
                "source_num": source_num,
                "title": title,
                "begin_time": begin_time,
                "end_time": end_time,
                "type": content_type,
                "relevance": round(relevance, 3),
            })

        sources_text = "\n\n".join(sources_lines) if sources_lines else "No relevant sources found in the lecture."
        return citations, sources_text

    def _get_summary_section(self) -> str:
        """Get the video summary as optional context."""
        from api.models import KnowledgeSummary

        try:
            summary = KnowledgeSummary.objects.get(video_id=self.video_id)
            return (
                f"### Lecture Overview\n{summary.overview}\n\n"
                f"**Key Topics:** {', '.join(summary.key_topics)}\n"
                f"**Difficulty:** {summary.difficulty_level}"
            )
        except KnowledgeSummary.DoesNotExist:
            return ""

    def _get_video_title(self) -> str:
        from api.models import Video
        try:
            return Video.objects.get(id=self.video_id).title
        except Exception:
            return "Unknown Video"

    def _build_messages(
        self, question: str, chat_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        """
        Build the full message list for the LLM call.

        Returns:
            (messages, citations)
        """
        citations, sources_text = self._retrieve_context(question)
        summary_section = self._get_summary_section()
        video_title = self._get_video_title()

        context = RAG_CONTEXT_TEMPLATE.format(
            video_title=video_title,
            summary_section=summary_section,
            sources_section=sources_text,
            question=question,
        )

        messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]

        # Include recent chat history for multi-turn context
        if chat_history:
            # Keep last 6 messages to stay within context limits
            for msg in chat_history[-6:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        messages.append({"role": "user", "content": context})

        return messages, citations

    def ask(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Ask a question and get a complete answer with citations.

        Args:
            question: The student's question.
            chat_history: Previous messages for multi-turn context.

        Returns:
            (answer_text, citations_list)
        """
        from api.llm_client import get_llm_client

        messages, citations = self._build_messages(question, chat_history)
        llm = get_llm_client(model="qwen3-max")
        answer = llm.chat_messages(messages, temperature=0.5, max_tokens=2048)
        return answer, citations

    def ask_stream(
        self,
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Tuple[str, Optional[List[Dict[str, Any]]]], None, None]:
        """
        Ask a question and stream the answer token-by-token.
        Citations are yielded as the LAST item (as a special signal).

        Yields:
            ("token", None) for each text chunk
            ("", citations_list) as the final yield with citations
        """
        from api.llm_client import get_llm_client

        messages, citations = self._build_messages(question, chat_history)
        llm = get_llm_client(model="qwen3-max")

        try:
            for token in llm.stream_chat_messages(
                messages, temperature=0.5, max_tokens=2048
            ):
                yield (token, None)
        except Exception as e:
            logger.error(f"RAG streaming failed: {e}")
            yield (f"Error: {e}", None)

        # Yield citations as final signal
        yield ("", citations)
