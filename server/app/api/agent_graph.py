"""
LangGraph-based ReAct agent for multi-step lecture Q&A.

Implements a plan-tool_call-observe-respond loop:
1. LLM decides whether to call a tool or respond directly
2. If tool call: execute tool, feed observation back to LLM
3. Repeat until LLM produces a final response (max 5 iterations)

The agent has access to tools defined in agent_tools.py:
- search_knowledge: semantic search over lecture content
- get_section_details: get full section transcript + knowledge points
- get_lecture_summary: get video-level summary
- list_sections: list all sections with titles
- get_transcript_at_time: get transcript around a timestamp

Usage:
    from api.agent_graph import run_agent, run_agent_stream

    # Non-streaming
    result = run_agent(video_id, question, chat_history)

    # Streaming (yields SSE events)
    for event in run_agent_stream(video_id, question, chat_history):
        print(event)
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional, Generator, Tuple

logger = logging.getLogger('LectureMind')


AGENT_SYSTEM_PROMPT = """You are an expert teaching assistant for a video lecture. You help students understand lecture content by using available tools to find relevant information before answering.

## Your Process:
1. **Analyze** the student's question to understand what information you need
2. **Select the right tool** based on question type (see guidelines below)
3. **Search** the lecture content using the appropriate tool
4. **Synthesize** the retrieved information into a clear, educational answer

## Tool Selection Guidelines:

**Use `search_slides` for:**
- Course logistics: tutors, teaching assistants, office hours
- Contact information: emails, phone numbers, office locations
- Course schedules: assignment deadlines, exam dates, weekly topics
- Visual content: diagrams, tables, charts shown on slides
- Administrative information from intro/outro slides

**Use `search_knowledge` for:**
- Conceptual questions: definitions, explanations, theories
- Technical topics: algorithms, methods, frameworks
- Lecture content: what was taught, explained, or discussed

**Use `get_lecture_summary` for:**
- General overview questions: "what does this lecture cover?"
- High-level structure and main topics

**Use `list_sections` for:**
- Finding which section covers a particular topic
- Understanding lecture organization

**Use `get_section_details` for:**
- Deep-dive into a specific section's content
- Getting full transcript of a particular part

**Use `get_transcript_at_time` for:**
- Specific timestamp questions: "what was said at 05:30?"

## Rules:
- ALWAYS use at least one tool before answering — do not guess or make up information
- Choose the RIGHT tool for the question type (slides for logistics, knowledge for concepts)
- You may call multiple tools if needed for a thorough answer
- When citing lecture content, ONLY mention time ranges that appear in the tool results
- NEVER fabricate section names, timestamps, or specific examples that aren't in the retrieved content
- If the retrieved content doesn't contain specific timestamps, do not invent them
- Use markdown formatting for clarity
- Be educational, patient, and thorough

## Citation Guidelines:
- Only cite specific timestamps [MM:SS] if they appear in the tool results
- If no specific timestamps are available, provide a general answer without fabricated citations
- Do not make up section titles or lecture structure details"""


class AgentRunner:
    """
    Runs a ReAct (Reasoning + Acting) loop using the OpenAI function-calling API.
    No LangGraph/LangChain dependency — pure implementation using our LLMClient.
    """

    MAX_ITERATIONS = 5

    def __init__(self, video_id: str, chat_history: Optional[List[Dict[str, str]]] = None):
        self.video_id = video_id
        self.chat_history = chat_history or []

    def _build_initial_messages(self, question: str) -> List[Dict[str, str]]:
        messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}]
        # Add recent chat history
        for msg in self.chat_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": question})
        return messages

    def run(self, question: str) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Run the agent loop (non-streaming).

        Returns:
            (final_answer, tool_steps, citations)
            - tool_steps: list of {"tool": name, "args": {}, "result": "..."}
            - citations: extracted from tool results
        """
        from api.llm_client import get_llm_client
        from api.agent_tools import make_tools, execute_tool

        llm = get_llm_client(model="qwen3-max")
        tools = make_tools(self.video_id)
        messages = self._build_initial_messages(question)
        tool_steps = []
        citations = []

        for iteration in range(self.MAX_ITERATIONS):
            # Call LLM with tools
            response = self._call_with_tools(llm, messages, tools)

            if response["type"] == "text":
                # LLM produced final answer - sanitize for hallucinations
                raw_answer = response["content"]
                sanitized_answer = self._sanitize_answer(raw_answer, tool_steps)
                citations = self._extract_citations_from_steps(tool_steps)
                return sanitized_answer, tool_steps, citations

            elif response["type"] == "tool_calls":
                # Process each tool call
                for tc in response["tool_calls"]:
                    tool_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    result = execute_tool(self.video_id, tool_name, args)
                    tool_steps.append({
                        "tool": tool_name,
                        "args": args,
                        "result": result[:1500],  # truncate for context
                    })

                    # Add to messages for next iteration
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tc],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result[:1500],
                    })

        # If we hit max iterations, ask LLM to summarize
        messages.append({
            "role": "user",
            "content": "Please provide your final answer based on all the information gathered so far."
        })
        response = self._call_with_tools(llm, messages, [])  # no tools, force text response
        raw_answer = response.get("content", "I was unable to find a complete answer.")
        sanitized_answer = self._sanitize_answer(raw_answer, tool_steps)
        citations = self._extract_citations_from_steps(tool_steps)
        return sanitized_answer, tool_steps, citations

    def run_stream(
        self, question: str
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Run the agent loop with streaming.

        Yields SSE-compatible event dicts:
            {"event": "thinking", "data": {"thought": "..."}}
            {"event": "tool_call", "data": {"tool": "...", "args": {...}}}
            {"event": "tool_result", "data": {"tool": "...", "result": "..."}}
            {"event": "token", "data": {"token": "..."}}
            {"event": "citations", "data": {"citations": [...]}}
            {"event": "done", "data": {"tool_steps": [...]}}
        """
        from api.llm_client import get_llm_client
        from api.agent_tools import make_tools, execute_tool

        llm = get_llm_client(model="qwen3-max")
        tools = make_tools(self.video_id)
        messages = self._build_initial_messages(question)
        tool_steps = []

        for iteration in range(self.MAX_ITERATIONS):
            yield {"event": "thinking", "data": {
                "thought": f"Analyzing question (step {iteration + 1})..."
            }}

            response = self._call_with_tools(llm, messages, tools)

            if response["type"] == "text":
                # Stream the final answer token by token
                yield {"event": "thinking", "data": {"thought": "Composing answer..."}}

                # Re-do as streaming for the final response
                for token in self._stream_final_answer(llm, messages):
                    yield {"event": "token", "data": {"token": token}}

                citations = self._extract_citations_from_steps(tool_steps)
                yield {"event": "citations", "data": {"citations": citations}}
                yield {"event": "done", "data": {"tool_steps": tool_steps}}
                return

            elif response["type"] == "tool_calls":
                for tc in response["tool_calls"]:
                    tool_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    yield {"event": "tool_call", "data": {
                        "tool": tool_name, "args": args
                    }}

                    result = execute_tool(self.video_id, tool_name, args)
                    truncated = result[:1500]
                    tool_steps.append({
                        "tool": tool_name, "args": args, "result": truncated,
                    })

                    yield {"event": "tool_result", "data": {
                        "tool": tool_name,
                        "result": truncated[:300] + ("..." if len(truncated) > 300 else ""),
                    }}

                    messages.append({
                        "role": "assistant", "content": None,
                        "tool_calls": [tc],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": truncated,
                    })

        # Max iterations reached — force final answer
        messages.append({
            "role": "user",
            "content": "Please provide your final answer based on all the information gathered."
        })
        for token in self._stream_final_answer(llm, messages, tools=[]):
            yield {"event": "token", "data": {"token": token}}

        citations = self._extract_citations_from_steps(tool_steps)
        yield {"event": "citations", "data": {"citations": citations}}
        yield {"event": "done", "data": {"tool_steps": tool_steps}}

    def _call_with_tools(
        self, llm, messages: List[Dict], tools: List[Dict]
    ) -> Dict[str, Any]:
        """Call LLM with function-calling tools. Returns parsed response."""
        if not llm._client:
            raise RuntimeError("LLM client not initialized")

        kwargs = {
            "model": llm.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = llm._client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            if choice.message.tool_calls:
                return {
                    "type": "tool_calls",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in choice.message.tool_calls
                    ]
                }
            else:
                return {
                    "type": "text",
                    "content": choice.message.content or "",
                }
        except Exception as e:
            logger.error(f"Agent LLM call failed: {e}")
            return {"type": "text", "content": f"Error: {e}"}

    def _stream_final_answer(
        self, llm, messages: List[Dict], tools: Optional[List] = None
    ) -> Generator[str, None, None]:
        """Stream the final LLM response token by token."""
        if not llm._client:
            yield "Error: LLM client not initialized"
            return

        kwargs = {
            "model": llm.model,
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": 2048,
            "stream": True,
        }
        # Don't pass tools for final streaming — force text output
        try:
            stream = llm._client.chat.completions.create(**kwargs)
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Agent streaming failed: {e}")
            yield f"Error: {e}"

    def _extract_citations_from_steps(
        self, tool_steps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract time-based citations from tool results (for search_knowledge and search_slides results)."""
        import re
        citations = []
        seen = set()

        for step in tool_steps:
            if step["tool"] == "search_knowledge":
                # Parse the formatted search results
                result = step.get("result", "")
                # Pattern: [Result N] (type) "title" [MM:SS - MM:SS]
                pattern = r'\[Result \d+\]\s*\((\w+)\)\s*"([^"]+)"\s*\[(\d+:\d+)\s*-\s*(\d+:\d+)\]'
                for match in re.finditer(pattern, result):
                    ctype, title, begin_str, end_str = match.groups()

                    # Parse mm:ss
                    bp = begin_str.split(":")
                    ep = end_str.split(":")
                    begin_time = int(bp[0]) * 60 + int(bp[1])
                    end_time = int(ep[0]) * 60 + int(ep[1])

                    key = f"{title}-{begin_time}"
                    if key not in seen:
                        seen.add(key)
                        citations.append({
                            "source_num": len(citations) + 1,
                            "title": title,
                            "begin_time": float(begin_time),
                            "end_time": float(end_time),
                            "type": ctype,
                            "relevance": 0.8,
                        })

            elif step["tool"] == "search_slides":
                # Parse slide search results
                result = step.get("result", "")
                # Pattern: [Slide N] [MM:SS] or [Slide @ MM:SS]
                pattern = r'\[Slide(?:\s+\d+)?\s*@?\s*(\d+:\d+)\]'
                for match in re.finditer(pattern, result):
                    time_str = match.group(1)
                    bp = time_str.split(":")
                    begin_time = int(bp[0]) * 60 + int(bp[1])

                    key = f"slide-{begin_time}"
                    if key not in seen:
                        seen.add(key)
                        citations.append({
                            "source_num": len(citations) + 1,
                            "title": "Slide",
                            "begin_time": float(begin_time),
                            "end_time": float(begin_time) + 5,  # Slides typically shown for a few seconds
                            "type": "slide",
                            "relevance": 0.85,
                        })

            elif step["tool"] == "get_section_details":
                # Parse section time range
                result = step.get("result", "")
                time_match = re.search(r'Time:\s*(\d+:\d+)\s*-\s*(\d+:\d+)', result)
                title_match = re.search(r'## Section \d+:\s*(.+)', result)
                if time_match:
                    bp = time_match.group(1).split(":")
                    ep = time_match.group(2).split(":")
                    begin_time = int(bp[0]) * 60 + int(bp[1])
                    end_time = int(ep[0]) * 60 + int(ep[1])
                    title = title_match.group(1).strip() if title_match else "Section"
                    key = f"section-{begin_time}"
                    if key not in seen:
                        seen.add(key)
                        citations.append({
                            "source_num": len(citations) + 1,
                            "title": title,
                            "begin_time": float(begin_time),
                            "end_time": float(end_time),
                            "type": "section",
                            "relevance": 0.9,
                        })

        return citations

    def _sanitize_answer(self, answer: str, tool_steps: List[Dict[str, Any]]) -> str:
        """
        Sanitize the answer to remove hallucinated citations.
        Only keeps citations that match actual tool results.
        """
        import re

        # Extract all valid time ranges from tool results
        valid_time_ranges = set()
        for step in tool_steps:
            result = step.get("result", "")
            # Find all time ranges in tool results [MM:SS - MM:SS] or at MM:SS
            time_pattern = r'(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})'
            for match in re.finditer(time_pattern, result):
                valid_time_ranges.add(match.group(0))

        # Check for potential hallucinated citations
        # Pattern: "at MM:SS-MM:SS" or "[MM:SS - MM:SS]" or section references
        citation_patterns = [
            r'at\s+\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}',
            r'\[\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\]',
            r'\(\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}\)',
        ]

        sanitized = answer
        hallucination_indicators = []

        for pattern in citation_patterns:
            for match in re.finditer(pattern, answer):
                citation = match.group(0)
                # Check if this citation exists in valid results
                is_valid = any(
                    range_str in citation or citation in range_str
                    for range_str in valid_time_ranges
                )
                if not is_valid:
                    hallucination_indicators.append(citation)

        # If we found likely hallucinations, add a note and remove specific timestamps
        if hallucination_indicators:
            logger.warning(f"Potential hallucinated citations detected: {hallucination_indicators}")
            # Remove specific timestamp citations that don't match tool results
            for citation in hallucination_indicators:
                sanitized = sanitized.replace(citation, "")
            # Clean up any double spaces or empty parentheses left behind
            sanitized = re.sub(r'\s+', ' ', sanitized)
            sanitized = re.sub(r'\(\s*\)', '', sanitized)
            sanitized = re.sub(r'\[\s*\]', '', sanitized)

        return sanitized.strip()


def run_agent(
    video_id: str,
    question: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Convenience function: run agent non-streaming."""
    runner = AgentRunner(video_id, chat_history)
    return runner.run(question)


def run_agent_stream(
    video_id: str,
    question: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Convenience function: run agent with streaming events."""
    runner = AgentRunner(video_id, chat_history)
    yield from runner.run_stream(question)
