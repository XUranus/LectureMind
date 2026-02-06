"""
Hybrid lecture video chunker using slide change times + ASR transcript.

Input:
  - slide_change_times: List[float] (seconds)
  - asr_transcript: Dict from Qwen ASR (with 'transcripts' -> 'sentences')
Output:
  - List[Tuple[float, float]]: [(start_sec, end_sec), ...]
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from collections import defaultdict

# Optional: only import if semantic check is enabled
try:
    from sentence_transformers import SentenceTransformer, util
    _SENTENCE_TRANSFORMER_AVAILABLE = True
except ImportError:
    _SENTENCE_TRANSFORMER_AVAILABLE = False
    print("Warning: sentence-transformers not installed. Semantic check disabled.")

import logging

logger = logging.getLogger(__name__)


def detect_silence_gaps(
    sentences: List[Dict[str, Any]],
    min_gap_sec: float = 2.0
) -> List[float]:
    """Detect long silences between spoken sentences."""
    gaps = []
    for i in range(len(sentences) - 1):
        end_current = sentences[i]["end_time"] / 1000.0  # ms → sec
        start_next = sentences[i + 1]["begin_time"] / 1000.0
        gap = start_next - end_current
        if gap >= min_gap_sec:
            gaps.append((end_current + start_next) / 2.0)  # midpoint as split candidate
    return gaps


def extract_text_in_window(
    sentences: List[Dict[str, Any]],
    center_sec: float,
    window_sec: float
) -> str:
    """Extract all text within [center - window, center + window]."""
    start_win = center_sec - window_sec
    end_win = center_sec + window_sec
    texts = []
    for s in sentences:
        s_start = s["begin_time"] / 1000.0
        s_end = s["end_time"] / 1000.0
        # Include sentence if it overlaps the window
        if s_end >= start_win and s_start <= end_win:
            texts.append(s["text"].strip())
    return " ".join(texts)


def is_semantic_shift(
    sentences: List[Dict[str, Any]],
    t_sec: float,
    window_sec: float = 1.5,
    similarity_threshold: float = 0.6,
    model: Optional["SentenceTransformer"] = None
) -> bool:
    """
    Determine if there's a topic shift around time t_sec.
    Returns True if a split is semantically justified.
    """
    if not _SENTENCE_TRANSFORMER_AVAILABLE or model is None:
        # Fallback: always accept if no semantic model
        return True

    pre_text = extract_text_in_window(sentences, t_sec - window_sec, window_sec)
    post_text = extract_text_in_window(sentences, t_sec + window_sec, window_sec)

    # If either side has no speech, treat as valid break
    if not pre_text.strip() or not post_text.strip():
        return True

    try:
        emb_pre = model.encode(pre_text, convert_to_tensor=True)
        emb_post = model.encode(post_text, convert_to_tensor=True)
        sim = util.cos_sim(emb_pre, emb_post).item()
        return sim < similarity_threshold
    except Exception as e:
        logger.warning(f"Semantic check failed at {t_sec:.2f}s: {e}")
        return True  # conservative: accept split on error


def hybrid_chunk(
    slide_change_times: List[float],
    asr_transcript: Dict[str, Any],
    video_duration_sec: float,
    tolerance_window: float = 1.5,
    min_chunk_duration: float = 10.0,
    silence_gap_threshold: float = 2.0,
    semantic_similarity_threshold: float = 0.6,
    use_semantic_check: bool = True,
) -> List[Tuple[float, float]]:
    """
    Generate hybrid chunks using slide changes + ASR semantics.

    Args:
        slide_change_times: Slide switch times in seconds.
        asr_transcript: Full ASR result from Qwen (JSON dict).
        video_duration_sec: Total duration of the video (seconds).
        tolerance_window: Time window (sec) around candidate to inspect speech.
        min_chunk_duration: Minimum allowed chunk length (sec).
        silence_gap_threshold: Min silence (sec) to consider as candidate.
        semantic_similarity_threshold: Below this → topic shift.
        use_semantic_check: Enable semantic filtering (requires sentence-transformers).

    Returns:
        List of (start_sec, end_sec) tuples.
    """
    # Extract sentences
    sentences = []
    for tr in asr_transcript.get("transcripts", []):
        sentences.extend(tr.get("sentences", []))
    if not sentences:
        logger.warning("No sentences found in ASR transcript. Falling back to slide-only chunks.")
        candidates = sorted(set(slide_change_times))
    else:
        # Step 1: Detect silence gaps
        silence_gaps = detect_silence_gaps(sentences, min_gap_sec=silence_gap_threshold)

        # Step 2: Combine candidates
        candidates = sorted(set(slide_change_times + silence_gaps))

        # Step 3: Load embedding model if needed
        model = None
        if use_semantic_check and _SENTENCE_TRANSFORMER_AVAILABLE:
            model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

        # Step 4: Filter candidates
        filtered_candidates = []
        last_split = 0.0

        for t in candidates:
            if t <= last_split + min_chunk_duration:
                continue  # too close to last split

            # Check semantic shift (or fallback to accept)
            if use_semantic_check:
                if not is_semantic_shift(
                    sentences,
                    t,
                    window_sec=tolerance_window,
                    similarity_threshold=semantic_similarity_threshold,
                    model=model
                ):
                    continue  # reject: same topic continues

            filtered_candidates.append(t)
            last_split = t

        candidates = filtered_candidates

    # Step 5: Build final chunks
    boundaries = [0.0] + candidates + [video_duration_sec]
    chunks = []
    i = 0
    while i < len(boundaries) - 1:
        start = boundaries[i]
        end = boundaries[i + 1]

        # Merge small chunks
        while (end - start) < min_chunk_duration and (i + 2) < len(boundaries):
            i += 1
            end = boundaries[i + 1]

        chunks.append((start, end))
        i += 1

    logger.info(f"Generated {len(chunks)} hybrid chunks.")
    return chunks