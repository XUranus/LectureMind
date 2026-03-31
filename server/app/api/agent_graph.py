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
2. **Search** the lecture content using the available tools
3. **Synthesize** the retrieved information into a clear, educational answer

## Rules:
- ALWAYS use at least one tool before answering — do not guess or make up information
- For conceptual questions, use `search_knowledge` to find relevant knowledge points
- For structural questions ("what does the lecture cover?"), use `get_lecture_summary` or `list_sections`
- For specific timestamp questions, use `get_transcript_at_time`
- For deep-dive into a section, use `get_section_details`
- You may call multiple tools if needed for a thorough answer
- When citing lecture content, mention the time range (e.g., "at 05:30-08:15")
- Use markdown formatting for clarity
- Be educational, patient, and thorough"""


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
                # LLM produced final answer
                citations = self._extract_citations_from_steps(tool_steps)
                return response["content"], tool_steps, citations

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
        citations = self._extract_citations_from_steps(tool_steps)
        return response.get("content", "I was unable to find a complete answer."), tool_steps, citations

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
        """Extract time-based citations from tool results (for search_knowledge results)."""
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
