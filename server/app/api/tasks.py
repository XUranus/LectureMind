# api/tasks.py
"""
Async task implementations with strict input/output contracts.
All functions must:
- Accept Dict[str, Any] input
- Return Dict[str, Any] result
- Raise exceptions on failure (runner handles status updates)
- Include video_id in output for downstream tasks
"""
import logging
import re
from typing import Dict, Any, Callable, List
from django.utils import timezone
import json
import os
import uuid
from django.core.files import File
from django.conf import settings
from api.utils import generate_thumbnails_for_video, get_local_file_path
from api.models import (
    Video, Thumbnail, VideoTranscript, TranscriptSentence,
    VideoSection, KnowledgePoint,
)

from api.dashscope_asr import DashScopeASRClient
from api.lecture_video_slides_chunker import detect_slide_changes_multithreaded
from api.lecture_video_hybrid_chunker import hybrid_chunk
from api.utils import generate_master_playlist, generate_hls_renditions

logger = logging.getLogger('polyu-video')


# ======================
# PROMPT TEMPLATES
# ======================

FINE_GRAINED_EXTRACTION_PROMPT = """You are an expert educational content analyst. Analyze the following lecture segment and extract structured knowledge points.

Section: {section_title}
Time range: {time_range}

Transcript:
---
{transcript}
---

Extract the following in JSON format:
{{
  "section_title": "A concise, descriptive title for this lecture segment (5-10 words)",
  "points": [
    {{
      "title": "Knowledge point title (concise, 3-8 words)",
      "summary": "2-3 sentence explanation of this concept as taught in this segment",
      "terms": ["key technical term 1", "key technical term 2"],
      "importance": 0.0-1.0
    }}
  ]
}}

Rules:
- Extract 1-5 knowledge points per segment
- Each point should be self-contained and understandable without the transcript
- Key terms should be specific technical vocabulary mentioned in the segment
- Importance reflects how central the concept is to the segment (0.0 = tangential, 1.0 = core topic)
- The section_title should describe what the segment covers, not be generic like "Section 1"
- If the transcript is too short or uninformative, return fewer points
- Return ONLY valid JSON, no markdown fences or other text"""


# ======================
# HELPER FUNCTIONS
# ======================

def save_transcript(video_id: str, data: Dict[str, Any]) -> None:
    """Save the ASR result data into the Django database."""
    video_transcript, created = VideoTranscript.objects.update_or_create(
        video_id=video_id,
        defaults={
            "file_url": data.get("file_url", ""),
            "format": data.get("audio_info", {}).get("format", ""),
            "sample_rate": data.get("audio_info", {}).get("sample_rate", 0),
        }
    )

    for transcript in data.get("transcripts", []):
        channel_id = transcript.get("channel_id", 0)
        TranscriptSentence.objects.filter(
            video_transcript=video_transcript, channel_id=channel_id
        ).delete()
        for sentence in transcript.get("sentences", []):
            TranscriptSentence.objects.create(
                video_transcript=video_transcript,
                channel_id=channel_id,
                sentence_id=sentence.get("sentence_id", 0),
                begin_time=sentence.get("begin_time", 0),
                end_time=sentence.get("end_time", 0),
                language=sentence.get("language", ""),
                emotion=sentence.get("emotion", ""),
                text=sentence.get("text", "")
            )


def update_thumbnails_for_video(video_id: str, thumbnail_data: list[dict]):
    """Replace all thumbnails for a video with new ones."""
    try:
        video_uuid = uuid.UUID(video_id)
        video = Video.objects.get(id=video_uuid)
    except (ValueError, Video.DoesNotExist) as e:
        raise ValueError(f"Invalid or missing video ID: {video_id}") from e

    old_thumbnails = Thumbnail.objects.filter(video=video)
    for thumb in old_thumbnails:
        if thumb.image and os.path.isfile(thumb.image.path):
            os.remove(thumb.image.path)
    old_thumbnails.delete()

    created_count = 0
    for item in thumbnail_data:
        try:
            img_id = uuid.UUID(item['image_id'])
            time_sec = float(item['time_second'])
            img_path = item['image']

            if not os.path.isfile(img_path):
                logger.warning(f"Image not found: {img_path}")
                continue

            thumb = Thumbnail(id=img_id, video=video, time_second=time_sec)
            with open(img_path, 'rb') as f:
                thumb.image.save(os.path.basename(img_path), File(f), save=True)
            created_count += 1
        except (KeyError, ValueError, TypeError, OSError) as e:
            logger.warning(f"Skipping invalid thumbnail entry {item}: {e}")
            continue

    return created_count


def _get_transcript_as_asr_dict(video_id: str) -> Dict[str, Any]:
    """Fetch transcript from DB and reconstruct the ASR dict format."""
    try:
        vt = VideoTranscript.objects.get(video_id=video_id)
    except VideoTranscript.DoesNotExist:
        logger.warning(f"No transcript found for video {video_id}")
        return {"transcripts": []}

    sentences = TranscriptSentence.objects.filter(
        video_transcript=vt
    ).order_by('begin_time')

    sentence_list = [
        {
            "sentence_id": s.sentence_id,
            "begin_time": s.begin_time,
            "end_time": s.end_time,
            "language": s.language,
            "emotion": s.emotion,
            "text": s.text,
        }
        for s in sentences
    ]

    return {
        "file_url": vt.file_url,
        "audio_info": {"format": vt.format, "sample_rate": vt.sample_rate},
        "transcripts": [{"channel_id": 0, "sentences": sentence_list}],
    }


def _extract_transcript_for_range(sentences: list, begin_sec: float, end_sec: float) -> str:
    """Extract concatenated transcript text for a time range (sentences in ms)."""
    texts = []
    begin_ms = begin_sec * 1000
    end_ms = end_sec * 1000
    for s in sentences:
        s_begin = s.get("begin_time", 0)
        s_end = s.get("end_time", 0)
        if s_end >= begin_ms and s_begin <= end_ms:
            texts.append(s.get("text", "").strip())
    return " ".join(texts)


def _find_closest_thumbnail(video_id: str, time_sec: float):
    """Find the thumbnail closest to a given timestamp."""
    thumbnails = Thumbnail.objects.filter(video_id=video_id).order_by('time_second')
    if not thumbnails.exists():
        return None

    closest = None
    min_diff = float('inf')
    for thumb in thumbnails:
        diff = abs(thumb.time_second - time_sec)
        if diff < min_diff:
            min_diff = diff
            closest = thumb
    return closest


def _parse_llm_json(response_text: str) -> Dict[str, Any]:
    """
    Robustly parse JSON from an LLM response.
    Handles markdown fences, extra text, etc.
    """
    # Strip markdown code fences
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (with optional language tag)
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object in the text
    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {response_text[:300]}")


# ======================
# TASK IMPLEMENTATIONS
# ======================

def task_extract_audio_and_transcript(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract audio, upload to COS, transcribe with Qwen-ASR."""
    video_id = input_data['video_id']
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[ASR Task] Processing video {video_id}")

    from pydub import AudioSegment
    wav_file = os.path.join(settings.MEDIA_ROOT, "audio", f"{video_id}.wav")
    os.makedirs(os.path.dirname(wav_file), exist_ok=True)
    audio = AudioSegment.from_file(video_file, format="mp4")
    audio = audio.set_frame_rate(16000).set_channels(1)
    audio.export(wav_file, format="wav")

    from qcloud_cos import CosConfig, CosS3Client
    config = CosConfig(
        Region=os.environ['COS_REGION'],
        SecretId=os.environ['COS_SECRECT_ID'],
        SecretKey=os.environ['COS_SECRECT_KEY']
    )
    client = CosS3Client(config)
    bucket = os.environ['COS_BUCKET']
    cos_key = f'audio/{video_id}.wav'
    client.upload_file(Bucket=bucket, LocalFilePath=wav_file, Key=cos_key)
    signed_url = client.get_presigned_url(
        Method='GET', Bucket=bucket, Key=cos_key, Expired=3600
    )

    asr_client = DashScopeASRClient(region="beijing")
    transcript = asr_client.transcribe_audio(
        file_url=signed_url, language="en", timeout=600.0
    )
    save_transcript(video_id, transcript)

    return {
        "video_id": input_data["video_id"],
        "file": input_data['file'],
        "cos_audio_url": signed_url,
    }


def task_hls_streaming(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate HLS multi-resolution streaming files."""
    video_id = input_data.get('video_id')
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[HLS Task] Generate HLS files, video_id: {video_id}")

    generate_hls_renditions(
        input_video_path=video_file, video_id=video_id,
        output_root="./media/streams"
    )
    master_m3u8_path = generate_master_playlist(
        video_id=video_id, output_root="./media/streams",
        output_filename="master-stream.m3u8"
    )

    return {"video_id": input_data["video_id"], "master_m3u8_path": master_m3u8_path}


def task_ssim_move_detection(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Use SSIM algorithm to detect video frame changes (slide transitions)."""
    video_id = input_data.get('video_id')
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[SSIM Task] Processing video_id: {video_id}")

    changes = detect_slide_changes_multithreaded(
        video_path=video_file, ssim_threshold=0.7,
        min_interval_sec=5.0, resize_width=240,
        sampling_fps=10.0, num_workers=16,
    )

    return {
        "video_id": input_data["video_id"],
        "file": input_data['file'],
        "changes": changes,
    }


def task_generate_thumbnails(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate video thumbnails at detected slide change timestamps."""
    video_id = input_data.get('video_id')
    video_file = get_local_file_path(input_data['file'])
    frames = input_data.get('changes')
    logger.info(f"[Thumbnails Task] Processing video id: {video_id}")

    thumbnails = generate_thumbnails_for_video(
        video_file=video_file, time_seconds=frames,
        width=200, output_dir="./media/thumbnails"
    )
    count = update_thumbnails_for_video(video_id, thumbnails)

    return {
        "video_id": input_data["video_id"],
        "file": input_data['file'],
        "changes": input_data.get('changes', []),
        "thumbnail_count": count,
    }


def task_hybrid_chunking(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Combine SSIM slide changes + ASR transcript for intelligent segmentation."""
    video_id = input_data['video_id']
    slide_changes = input_data.get('changes', [])
    logger.info(f"[Hybrid Chunking Task] Processing video {video_id}")

    video = Video.objects.get(id=video_id)
    video_duration = video.duration

    if video_duration <= 0:
        if slide_changes:
            video_duration = max(slide_changes) + 60.0
        else:
            last_sentence = TranscriptSentence.objects.filter(
                video_transcript__video_id=video_id
            ).order_by('-end_time').first()
            if last_sentence:
                video_duration = last_sentence.end_time / 1000.0 + 10.0
            else:
                video_duration = 3600.0
        logger.warning(f"Video duration was 0, estimated as {video_duration:.1f}s")

    asr_transcript = _get_transcript_as_asr_dict(video_id)
    all_sentences = []
    for tr in asr_transcript.get("transcripts", []):
        all_sentences.extend(tr.get("sentences", []))

    chunks = hybrid_chunk(
        slide_change_times=slide_changes,
        asr_transcript=asr_transcript,
        video_duration_sec=video_duration,
        min_chunk_duration=30.0,
        silence_gap_threshold=2.0,
        semantic_similarity_threshold=0.5,
        use_semantic_check=True,
    )

    VideoSection.objects.filter(video_id=video_id).delete()

    for i, (start, end) in enumerate(chunks):
        transcript_text = _extract_transcript_for_range(all_sentences, start, end)
        thumbnail = _find_closest_thumbnail(video_id, start)
        VideoSection.objects.create(
            video_id=video_id,
            title=f"Section {i + 1}",
            begin_time=start, end_time=end,
            transcript_text=transcript_text,
            thumbnail=thumbnail, order=i,
        )

    logger.info(f"[Hybrid Chunking Task] Created {len(chunks)} sections for video {video_id}")

    return {"video_id": video_id, "section_count": len(chunks)}


def task_fine_grained_knowledge(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured knowledge points from each video section using LLM.

    For each section:
    1. Build a prompt with the section's transcript text
    2. Call LLM to extract knowledge points as structured JSON
    3. Parse the response and save KnowledgePoint records
    4. Update section titles with LLM-generated titles

    Input: {"video_id": "uuid-str", ...}
    Output: {"video_id": "uuid-str", "knowledge_points_count": N, "sections_processed": M}
    """
    from api.llm_client import get_llm_client

    video_id = input_data['video_id']
    logger.info(f"[Fine-Grained Knowledge Task] Processing video {video_id}")

    sections = VideoSection.objects.filter(video_id=video_id).order_by('order')
    if not sections.exists():
        logger.warning(f"No sections found for video {video_id}")
        return {"video_id": video_id, "knowledge_points_count": 0, "sections_processed": 0}

    # Initialize LLM client
    llm = get_llm_client()

    # Clear existing knowledge points for this video (re-extraction)
    KnowledgePoint.objects.filter(video_id=video_id).delete()

    total_kp_count = 0
    sections_processed = 0

    for section in sections:
        # Skip sections with very little transcript
        if not section.transcript_text or len(section.transcript_text.strip()) < 20:
            logger.debug(f"Skipping section {section.order} - insufficient transcript")
            continue

        # Format time range
        begin_min = int(section.begin_time // 60)
        begin_sec = int(section.begin_time % 60)
        end_min = int(section.end_time // 60)
        end_sec = int(section.end_time % 60)
        time_range = f"{begin_min:02d}:{begin_sec:02d} - {end_min:02d}:{end_sec:02d}"

        # Build prompt
        # Truncate long transcripts to fit context window
        transcript_text = section.transcript_text
        if len(transcript_text) > 3000:
            transcript_text = transcript_text[:3000] + "... [truncated]"

        prompt = FINE_GRAINED_EXTRACTION_PROMPT.format(
            section_title=section.title,
            time_range=time_range,
            transcript=transcript_text,
        )

        try:
            # Call LLM
            response = llm.chat(
                prompt=prompt,
                system_prompt="You are an expert educational content analyst. Always respond with valid JSON only.",
                temperature=0.3,
                max_tokens=2048,
            )

            # Parse response
            knowledge_data = _parse_llm_json(response)

            # Update section title
            new_title = knowledge_data.get("section_title", "").strip()
            if new_title and new_title != section.title:
                section.title = new_title
                section.save(update_fields=['title'])
                logger.debug(f"Updated section {section.order} title: {new_title}")

            # Save knowledge points
            points = knowledge_data.get("points", [])
            for kp_data in points:
                title = kp_data.get("title", "").strip()
                summary = kp_data.get("summary", "").strip()

                if not title or not summary:
                    continue

                KnowledgePoint.objects.create(
                    section=section,
                    video_id=video_id,
                    title=title,
                    summary=summary,
                    key_terms=kp_data.get("terms", []),
                    importance=min(max(float(kp_data.get("importance", 0.5)), 0.0), 1.0),
                )
                total_kp_count += 1

            sections_processed += 1
            logger.info(
                f"[Fine-Grained Knowledge Task] Section {section.order} "
                f"({section.title}): extracted {len(points)} knowledge points"
            )

        except Exception as e:
            logger.error(
                f"[Fine-Grained Knowledge Task] Failed to process section {section.order}: {e}"
            )
            # Continue to next section — don't let one failure block others
            continue

    logger.info(
        f"[Fine-Grained Knowledge Task] Complete: {total_kp_count} knowledge points "
        f"from {sections_processed} sections for video {video_id}"
    )

    return {
        "video_id": video_id,
        "knowledge_points_count": total_kp_count,
        "sections_processed": sections_processed,
    }


def task_embed_knowledge(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate embeddings for knowledge points and transcript sentences,
    and store them in the ChromaDB vector store for semantic retrieval.

    Embeds:
    1. Each knowledge point (title + summary) with metadata
    2. Each section's transcript with metadata

    Input: {"video_id": "uuid-str", ...}
    Output: {"video_id": "uuid-str", "embedded_knowledge_points": N, "embedded_sections": M}
    """
    from api.vector_store import get_vector_store

    video_id = input_data['video_id']
    logger.info(f"[Embed Knowledge Task] Processing video {video_id}")

    store = get_vector_store()

    # Clean up existing embeddings for this video (re-embedding)
    store.delete_by_video(video_id)

    # 1. Embed knowledge points
    knowledge_points = KnowledgePoint.objects.filter(
        video_id=video_id
    ).select_related('section')

    kp_ids = []
    kp_texts = []
    kp_metas = []

    for kp in knowledge_points:
        embed_text = f"{kp.title}: {kp.summary}"
        if kp.key_terms:
            embed_text += f" (Key terms: {', '.join(kp.key_terms)})"

        kp_ids.append(str(kp.id))
        kp_texts.append(embed_text)
        kp_metas.append({
            "video_id": video_id,
            "section_id": str(kp.section_id),
            "type": "knowledge_point",
            "title": kp.title,
            "begin_time": kp.section.begin_time,
            "end_time": kp.section.end_time,
            "importance": kp.importance,
        })

    embedded_kp = 0
    if kp_ids:
        embedded_kp = store.upsert_batch(kp_ids, kp_texts, kp_metas)
        logger.info(f"[Embed Knowledge Task] Embedded {embedded_kp} knowledge points")

    # 2. Embed section transcripts
    sections = VideoSection.objects.filter(video_id=video_id).order_by('order')

    sec_ids = []
    sec_texts = []
    sec_metas = []

    for section in sections:
        if not section.transcript_text or len(section.transcript_text.strip()) < 10:
            continue

        # Truncate very long sections for embedding
        text = section.transcript_text
        if len(text) > 2000:
            text = text[:2000]

        sec_ids.append(f"section-{section.id}")
        sec_texts.append(text)
        sec_metas.append({
            "video_id": video_id,
            "section_id": str(section.id),
            "type": "section_transcript",
            "title": section.title,
            "begin_time": section.begin_time,
            "end_time": section.end_time,
        })

    embedded_sec = 0
    if sec_ids:
        embedded_sec = store.upsert_batch(sec_ids, sec_texts, sec_metas)
        logger.info(f"[Embed Knowledge Task] Embedded {embedded_sec} section transcripts")

    # Update embedding_id references on KnowledgePoint records
    for kp in knowledge_points:
        kp.embedding_id = str(kp.id)
    KnowledgePoint.objects.bulk_update(
        list(knowledge_points), ['embedding_id']
    )

    logger.info(
        f"[Embed Knowledge Task] Complete: {embedded_kp} KPs + "
        f"{embedded_sec} sections for video {video_id}"
    )

    return {
        "video_id": video_id,
        "embedded_knowledge_points": embedded_kp,
        "embedded_sections": embedded_sec,
    }


def task_generate_summary(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate AI summary using transcript and metadata.
    STUB: Will be replaced with real implementation in Phase 3.
    """
    logger.info(f"[Summary Task] Processing video {input_data.get('video_id')}")
    return {
        "video_id": input_data["video_id"],
        "summary": f"AI-generated summary for video {input_data['video_id']} "
                   f"created at {timezone.now().isoformat()}",
        "keywords": ["video", "summary", "ai", "processing"],
    }


# ======================
# TASK REGISTRY
# ======================
TASK_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "task_extract_audio_and_transcript": task_extract_audio_and_transcript,
    "task_hls_streaming": task_hls_streaming,
    "task_ssim_move_detection": task_ssim_move_detection,
    "task_generate_thumbnails": task_generate_thumbnails,
    "task_hybrid_chunking": task_hybrid_chunking,
    "task_fine_grained_knowledge": task_fine_grained_knowledge,
    "task_embed_knowledge": task_embed_knowledge,
    "task_generate_summary": task_generate_summary,
}


def get_task_function(func_name: str) -> Callable:
    """Safely retrieve task function from registry."""
    if func_name not in TASK_REGISTRY:
        raise ValueError(
            f"Unknown task function: {func_name}. "
            f"Registered: {list(TASK_REGISTRY.keys())}"
        )
    return TASK_REGISTRY[func_name]
