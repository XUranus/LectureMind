"""
Agent tool definitions for the LangGraph lecture assistant.

Each tool function:
- Takes simple parameters (strings, ints)
- Accesses Django models / vector store
- Returns a formatted string result the LLM can reason over

All tools are scoped to a single video_id (injected via closure).
"""
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger('LectureMind')


def _format_time(seconds: float) -> str:
    m, s = int(seconds // 60), int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def make_tools(video_id: str) -> List[Dict[str, Any]]:
    """
    Build the list of OpenAI-format tool definitions scoped to a video.
    Returns a list of function-calling tool schemas.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": (
                    "Semantic search over the lecture's knowledge points and transcript. "
                    "Use this when the student asks about a specific concept, term, or topic "
                    "covered in the lecture."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query — a concept, term, or question to look up"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return (default 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_section_details",
                "description": (
                    "Get the full details of a specific lecture section by its order number. "
                    "Use this when you need the complete transcript or knowledge points "
                    "for a particular section."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section_order": {
                            "type": "integer",
                            "description": "The section order number (0-indexed)"
                        }
                    },
                    "required": ["section_order"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_lecture_summary",
                "description": (
                    "Get the high-level summary of the entire lecture including overview, "
                    "key topics, learning objectives, and prerequisites. "
                    "Use this for general questions about what the lecture covers."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_sections",
                "description": (
                    "List all sections/chapters in the lecture with their titles and time ranges. "
                    "Use this to understand the lecture structure or find which section "
                    "covers a particular topic."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_transcript_at_time",
                "description": (
                    "Get the transcript text around a specific timestamp in the lecture. "
                    "Use this when you need to see exactly what was said at a particular moment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "time_seconds": {
                            "type": "number",
                            "description": "Timestamp in seconds to look up"
                        },
                        "window_seconds": {
                            "type": "number",
                            "description": "How many seconds of context around the timestamp (default 30)",
                            "default": 30
                        }
                    },
                    "required": ["time_seconds"]
                }
            }
        },
    ]


def execute_tool(video_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Execute a tool call and return the result as a string.
    This is called by the agent graph when the LLM decides to use a tool.
    """
    try:
        if tool_name == "search_knowledge":
            return _tool_search_knowledge(video_id, **arguments)
        elif tool_name == "get_section_details":
            return _tool_get_section_details(video_id, **arguments)
        elif tool_name == "get_lecture_summary":
            return _tool_get_lecture_summary(video_id)
        elif tool_name == "list_sections":
            return _tool_list_sections(video_id)
        elif tool_name == "get_transcript_at_time":
            return _tool_get_transcript_at_time(video_id, **arguments)
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return f"Tool execution error: {e}"


def _tool_search_knowledge(video_id: str, query: str, top_k: int = 5) -> str:
    """Semantic search over knowledge points and transcript."""
    from api.vector_store import get_vector_store

    store = get_vector_store()
    results = store.query(query_text=query, video_id=video_id, top_k=top_k)

    if not results:
        return "No relevant results found for this query."

    lines = []
    for i, r in enumerate(results):
        meta = r.get("metadata", {})
        title = meta.get("title", "Unknown")
        begin = float(meta.get("begin_time", 0))
        end = float(meta.get("end_time", 0))
        ctype = meta.get("type", "unknown")
        relevance = r.get("relevance", 0)
        text = r.get("text", "")[:400]

        lines.append(
            f"[Result {i+1}] ({ctype}) \"{title}\" "
            f"[{_format_time(begin)} - {_format_time(end)}] "
            f"(relevance: {relevance:.2f})\n{text}"
        )

    return "\n\n".join(lines)


def _tool_get_section_details(video_id: str, section_order: int) -> str:
    """Get full details of a specific section."""
    from api.models import VideoSection, KnowledgePoint

    try:
        section = VideoSection.objects.get(video_id=video_id, order=section_order)
    except VideoSection.DoesNotExist:
        return f"Section {section_order} not found."

    kps = KnowledgePoint.objects.filter(section=section).order_by('created_at')

    result = (
        f"## Section {section.order}: {section.title}\n"
        f"Time: {_format_time(section.begin_time)} - {_format_time(section.end_time)}\n\n"
        f"### Transcript:\n{section.transcript_text[:2000]}\n\n"
    )

    if kps.exists():
        result += "### Knowledge Points:\n"
        for kp in kps:
            terms = ", ".join(kp.key_terms) if kp.key_terms else ""
            result += (
                f"- **{kp.title}** (importance: {kp.importance:.1f})\n"
                f"  {kp.summary}\n"
                f"  Key terms: {terms}\n\n"
            )

    return result


def _tool_get_lecture_summary(video_id: str) -> str:
    """Get the video-level summary."""
    from api.models import KnowledgeSummary, Video

    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return "Video not found."

    try:
        summary = KnowledgeSummary.objects.get(video_id=video_id)
    except KnowledgeSummary.DoesNotExist:
        return f"No summary available for \"{video.title}\". The video may not have been fully processed."

    topics = ", ".join(summary.key_topics) if summary.key_topics else "N/A"
    objectives = "\n".join(f"- {o}" for o in summary.learning_objectives) if summary.learning_objectives else "N/A"
    prereqs = ", ".join(summary.prerequisites) if summary.prerequisites else "None"

    return (
        f"# Lecture Summary: {video.title}\n\n"
        f"**Overview:** {summary.overview}\n\n"
        f"**Key Topics:** {topics}\n\n"
        f"**Learning Objectives:**\n{objectives}\n\n"
        f"**Prerequisites:** {prereqs}\n\n"
        f"**Difficulty Level:** {summary.difficulty_level}"
    )


def _tool_list_sections(video_id: str) -> str:
    """List all sections with titles and time ranges."""
    from api.models import VideoSection

    sections = VideoSection.objects.filter(video_id=video_id).order_by('order')
    if not sections.exists():
        return "No sections found. The video may not have been processed yet."

    lines = ["# Lecture Sections\n"]
    for s in sections:
        kp_count = s.knowledge_points.count()
        lines.append(
            f"- **Section {s.order}:** {s.title} "
            f"[{_format_time(s.begin_time)} - {_format_time(s.end_time)}] "
            f"({kp_count} knowledge points)"
        )

    return "\n".join(lines)


def _tool_get_transcript_at_time(
    video_id: str, time_seconds: float, window_seconds: float = 30
) -> str:
    """Get transcript text around a timestamp."""
    from api.models import TranscriptSentence

    begin_ms = int((time_seconds - window_seconds / 2) * 1000)
    end_ms = int((time_seconds + window_seconds / 2) * 1000)

    sentences = TranscriptSentence.objects.filter(
        video_transcript__video_id=video_id,
        begin_time__gte=max(0, begin_ms),
        end_time__lte=end_ms,
    ).order_by('begin_time')

    if not sentences.exists():
        return f"No transcript found around {_format_time(time_seconds)}."

    lines = [
        f"# Transcript around {_format_time(time_seconds)} "
        f"(window: {window_seconds}s)\n"
    ]
    for s in sentences:
        t = _format_time(s.begin_time / 1000)
        lines.append(f"[{t}] {s.text}")

    return "\n".join(lines)
