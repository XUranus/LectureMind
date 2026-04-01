# Agent System — ReAct Multi-Step Reasoning

## Overview

The agent system (`agent_graph.py`) implements a ReAct (Reasoning + Acting) loop that enables the LLM to perform multi-step reasoning over lecture content. Unlike the single-shot RAG engine, the agent can decide which tools to call, inspect intermediate results, and iterate before producing a final answer.

## Class: `AgentRunner`

### Constructor

```python
runner = AgentRunner(video_id="uuid", chat_history=[...])
```

- `video_id`: Scopes all tool calls to a single video
- `chat_history`: Previous messages for multi-turn context (last 6 used)

### Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MAX_ITERATIONS` | 5 | Maximum tool-call rounds before forcing an answer |

## ReAct Loop

The core algorithm follows the Reasoning + Acting paradigm:

```
                    ┌─────────────────────────────┐
                    │     Build initial messages   │
                    │   system + history + question│
                    └──────────────┬──────────────┘
                                   │
            ┌──────────────────────▼──────────────────────┐
            │              Call LLM with tools            │◄───────┐
            └──────────────────────┬──────────────────────┘        │
                                   │                               │
                    ┌──────────────┴──────────────┐                │
                    │                             │                │
              response.type                 response.type          │
              == "text"                     == "tool_calls"        │
                    │                             │                │
                    ▼                             ▼                │
            ┌──────────────┐          ┌─────────────────────┐     │
            │ Final answer │          │  Execute each tool  │     │
            │ (stream it)  │          │  Append results to  │     │
            └──────┬───────┘          │  message history    │     │
                   │                  └──────────┬──────────┘     │
                   │                             │                │
                   │                    iteration < MAX?──────────┘
                   │                             │ no
                   │                  ┌──────────▼──────────┐
                   │                  │ Force final answer  │
                   │                  │ (no tools, stream)  │
                   │                  └──────────┬──────────┘
                   │                             │
                   └──────────────┬──────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │  Extract citations from    │
                    │  tool step results         │
                    └───────────────────────────┘
```

## Key Methods

### `run(question) → (answer, tool_steps, citations)`

Non-streaming execution. Returns the complete answer, all tool steps performed, and extracted citations.

### `run_stream(question) → Generator[event_dict]`

Streaming execution yielding SSE-compatible event dicts:

| Event | Payload | When |
|-------|---------|------|
| `thinking` | `{"thought": "Analyzing question (step 1)..."}` | Start of each iteration |
| `tool_call` | `{"tool": "search_knowledge", "args": {"query": "..."}}` | LLM decided to call a tool |
| `tool_result` | `{"tool": "...", "result": "preview..."}` | Tool execution completed (300-char preview) |
| `token` | `{"token": "partial text"}` | Final answer streaming |
| `citations` | `{"citations": [...]}` | After answer generation |
| `done` | `{"tool_steps": [...]}` | Completion with full tool history |

### `_call_with_tools(llm, messages, tools) → response_dict`

Single LLM call with OpenAI function-calling. Returns either:

```python
{"type": "text", "content": "The final answer..."}
# or
{"type": "tool_calls", "tool_calls": [{"id": "...", "function": {"name": "...", "arguments": "..."}}]}
```

Uses `tool_choice: "auto"` to let the LLM decide whether to call a tool or respond directly.

### `_stream_final_answer(llm, messages) → Generator[str]`

When the LLM has gathered enough information and produces a text response in the non-streaming `_call_with_tools`, this method re-does the same call as streaming to yield tokens one by one.

Tools are NOT passed in this call — forcing the LLM to produce text output only.

### `_extract_citations_from_steps(tool_steps) → citations_list`

Post-processes tool results to extract structured citations with timestamps:

**From `search_knowledge` results:**
Regex matches `[Result N] (type) "title" [MM:SS - MM:SS]` patterns.

**From `get_section_details` results:**
Regex matches `Time: MM:SS - MM:SS` and `## Section N: Title` patterns.

## System Prompt

```
You are an expert teaching assistant for a video lecture. You help students
understand lecture content by using available tools to find relevant
information before answering.

## Your Process:
1. **Analyze** the student's question to understand what information you need
2. **Search** the lecture content using the available tools
3. **Synthesize** the retrieved information into a clear, educational answer

## Rules:
- ALWAYS use at least one tool before answering
- For conceptual questions, use `search_knowledge`
- For structural questions, use `get_lecture_summary` or `list_sections`
- For specific timestamp questions, use `get_transcript_at_time`
- For deep-dive into a section, use `get_section_details`
- You may call multiple tools if needed
- When citing lecture content, mention the time range
- Use markdown formatting
- Be educational, patient, and thorough
```

## LLM Configuration (Agent)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Model | `qwen3-max` | Best reasoning + function-calling capability |
| Temperature (tool calls) | 0.3 | Deterministic tool selection |
| Temperature (final answer) | 0.5 | Slightly creative but grounded |
| Max tokens | 2048 | Sufficient for detailed answers |
| tool_choice | `"auto"` | LLM decides when to call tools vs respond |

## Example Execution Trace

Question: *"How does the lecture explain the relationship between learning rate and convergence?"*

```
Step 1: thinking — "Analyzing question (step 1)..."
Step 2: tool_call — search_knowledge(query="learning rate convergence")
Step 3: tool_result — "[Result 1] (knowledge_point) "Learning Rate..." ..."
Step 4: thinking — "Analyzing question (step 2)..."
Step 5: tool_call — get_section_details(section_order=3)
Step 6: tool_result — "## Section 3: Optimization Techniques..."
Step 7: thinking — "Composing answer..."
Step 8-N: token — "The lecture explains that the learning rate..."
Final: citations — [{source_num: 1, title: "Learning Rate", begin_time: 180, ...}]
Final: done — {tool_steps: [{tool: "search_knowledge", ...}, {tool: "get_section_details", ...}]}
```
