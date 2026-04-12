# api/tasks.py
"""
Async task implementations. All functions accept/return Dict[str, Any].
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
    VideoSection, KnowledgePoint, KnowledgeSummary, KnowledgeMindmap, SlideOCR,
)
from api.dashscope_asr import DashScopeASRClient
from api.lecture_video_slides_chunker import detect_slide_changes_multithreaded
from api.lecture_video_hybrid_chunker import hybrid_chunk
from api.utils import generate_master_playlist, generate_hls_renditions

logger = logging.getLogger('LectureMind')


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
- Key terms should be specific technical vocabulary
- Importance: 0.0 = tangential, 1.0 = core topic
- The section_title should describe what the segment covers
- Return ONLY valid JSON, no markdown fences"""


COARSE_SUMMARY_PROMPT = """You are an expert educational content analyst. Given the following lecture sections and their knowledge points, produce a comprehensive video-level summary.

Video title: {video_title}

Sections:
{sections_text}

Produce a JSON response:
{{
  "overview": "3-5 sentence high-level overview of the entire lecture",
  "key_topics": ["Topic 1", "Topic 2", ...],
  "learning_objectives": ["After watching, viewers will understand X", ...],
  "prerequisites": ["Linear algebra basics", "Calculus fundamentals", ...],
  "difficulty_level": "beginner|intermediate|advanced"
}}

Rules:
- The overview should synthesize all sections, not just concatenate summaries
- Key topics: 3-8 major themes
- Learning objectives: 3-6 practical outcomes
- Prerequisites: 1-4 assumed knowledge areas (can be empty for introductory content)
- Difficulty based on content complexity
- Return ONLY valid JSON"""


MINDMAP_PROMPT = """You are an expert educational content analyst. Given the following lecture sections and knowledge points, produce a hierarchical mindmap structure.

Video title: {video_title}

Sections and knowledge points:
{sections_text}

Produce a JSON mindmap tree:
{{
  "id": "root",
  "label": "{video_title}",
  "children": [
    {{
      "id": "topic-1",
      "label": "Main Topic Name",
      "children": [
        {{
          "id": "sub-1-1",
          "label": "Subtopic or Key Concept",
          "children": []
        }}
      ]
    }}
  ]
}}

Rules:
- The root node should be the video/lecture title
- Group related knowledge points into 2-6 main topic branches
- Each main topic can have 1-5 subtopics
- Subtopics can optionally have 1-3 leaf nodes for specific details
- Maximum depth: 4 levels (root -> topic -> subtopic -> detail)
- Each node must have a unique "id" field (use descriptive slugs like "topic-ml-basics")
- Labels should be concise (2-6 words)
- Organize by conceptual relationships, NOT by chronological section order
- Return ONLY valid JSON"""



SLIDE_OCR_PROMPT = """Extract ALL visible text content from this lecture slide image. 

Rules:
- Extract every piece of text you can see: titles, bullet points, paragraphs, labels, captions, equations, code snippets, table content, etc.
- Preserve the hierarchical structure using markdown formatting (headings, bullet points, numbered lists)
- For mathematical equations, use LaTeX notation (e.g., $E = mc^2$)
- For code snippets, use markdown code blocks with language annotation
- For tables, use markdown table format
- For diagrams/charts, describe the text labels and any visible data
- If the slide appears to be blank or contains only decorative elements with no readable text, respond with: [NO TEXT CONTENT]
- Do NOT describe the visual layout or design elements — only extract text content
- Return the extracted text directly, no JSON wrapping needed"""


# ======================
# HELPER FUNCTIONS
# ======================

def save_transcript(video_id: str, data: Dict[str, Any]) -> None:
    video_transcript, _ = VideoTranscript.objects.update_or_create(
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
    video = Video.objects.get(id=uuid.UUID(video_id))
    old_thumbs = Thumbnail.objects.filter(video=video)
    for t in old_thumbs:
        # Delete low-res image
        if t.image and os.path.isfile(t.image.path):
            os.remove(t.image.path)
        # Delete high-res image if exists
        if t.image_high_res and os.path.isfile(t.image_high_res.path):
            os.remove(t.image_high_res.path)
    old_thumbs.delete()
    count = 0
    for item in thumbnail_data:
        try:
            thumb = Thumbnail(
                id=uuid.UUID(item['image_id']), video=video,
                time_second=float(item['time_second'])
            )
            # Save low-res image (for web display)
            with open(item['image'], 'rb') as f:
                thumb.image.save(os.path.basename(item['image']), File(f), save=True)
            # Save high-res image (for OCR) if available
            if item.get('image_high_res') and os.path.isfile(item['image_high_res']):
                with open(item['image_high_res'], 'rb') as f:
                    thumb.image_high_res.save(os.path.basename(item['image_high_res']), File(f), save=True)
            thumb.save()
            count += 1
        except Exception as e:
            logger.warning(f"Skipping thumbnail: {e}")
    return count


def _get_transcript_as_asr_dict(video_id: str) -> Dict[str, Any]:
    try:
        vt = VideoTranscript.objects.get(video_id=video_id)
    except VideoTranscript.DoesNotExist:
        return {"transcripts": []}
    sentences = TranscriptSentence.objects.filter(video_transcript=vt).order_by('begin_time')
    return {
        "file_url": vt.file_url,
        "audio_info": {"format": vt.format, "sample_rate": vt.sample_rate},
        "transcripts": [{"channel_id": 0, "sentences": [
            {"sentence_id": s.sentence_id, "begin_time": s.begin_time,
             "end_time": s.end_time, "language": s.language,
             "emotion": s.emotion, "text": s.text} for s in sentences
        ]}],
    }


def _extract_transcript_for_range(sentences: list, begin_sec: float, end_sec: float) -> str:
    begin_ms, end_ms = begin_sec * 1000, end_sec * 1000
    return " ".join(
        s.get("text", "").strip() for s in sentences
        if s.get("end_time", 0) >= begin_ms and s.get("begin_time", 0) <= end_ms
    )


def _find_closest_thumbnail(video_id: str, time_sec: float):
    thumbnails = Thumbnail.objects.filter(video_id=video_id).order_by('time_second')
    closest, min_diff = None, float('inf')
    for t in thumbnails:
        d = abs(t.time_second - time_sec)
        if d < min_diff:
            min_diff, closest = d, t
    return closest


def _parse_llm_json(response_text: str) -> Dict[str, Any]:
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from LLM: {response_text[:300]}")



def _report_progress(video_id: str, func_name: str, progress: int) -> None:
    """Update the progress field of the currently running task."""
    from api.models import AsyncTaskItem
    try:
        AsyncTaskItem.objects.filter(
            video_id=video_id, func_name=func_name, status='running'
        ).update(progress=min(max(progress, 0), 100))
    except Exception as e:
        logger.debug(f"Failed to update progress: {e}")


def _format_time(seconds: float) -> str:
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"


def _tree_to_react_flow(tree: Dict[str, Any], x: float = 0, y: float = 0,
                         level: int = 0) -> tuple:
    """
    Convert a hierarchical tree into React Flow nodes + edges.
    Uses a top-down layout with horizontal spacing per level.
    """
    nodes = []
    edges = []

    node_id = tree.get("id", "root")
    label = tree.get("label", "")
    children = tree.get("children", [])

    # Style by level
    styles = [
        {"background": "#4F46E5", "color": "#fff", "fontSize": 16, "fontWeight": 700,
         "padding": "12px 24px", "borderRadius": 12, "border": "2px solid #3730A3"},
        {"background": "#7C3AED", "color": "#fff", "fontSize": 14, "fontWeight": 600,
         "padding": "8px 16px", "borderRadius": 8, "border": "2px solid #6D28D9"},
        {"background": "#2563EB", "color": "#fff", "fontSize": 13, "fontWeight": 500,
         "padding": "6px 14px", "borderRadius": 8, "border": "1px solid #1D4ED8"},
        {"background": "#F3F4F6", "color": "#374151", "fontSize": 12, "fontWeight": 400,
         "padding": "4px 12px", "borderRadius": 6, "border": "1px solid #D1D5DB"},
    ]
    style = styles[min(level, len(styles) - 1)]

    nodes.append({
        "id": node_id,
        "type": "default",
        "data": {"label": label},
        "position": {"x": x, "y": y},
        "style": style,
    })

    if children:
        y_spacing = 120
        # Calculate total width needed for children
        child_count = len(children)
        x_spacing = max(200, 280 - level * 40)
        total_width = (child_count - 1) * x_spacing
        start_x = x - total_width / 2

        for i, child in enumerate(children):
            child_x = start_x + i * x_spacing
            child_y = y + y_spacing

            edges.append({
                "id": f"e-{node_id}-{child.get('id', i)}",
                "source": node_id,
                "target": child.get("id", f"{node_id}-{i}"),
                "type": "smoothstep",
                "animated": level == 0,
                "style": {"stroke": "#94A3B8", "strokeWidth": 2},
            })

            child_nodes, child_edges = _tree_to_react_flow(
                child, x=child_x, y=child_y, level=level + 1
            )
            nodes.extend(child_nodes)
            edges.extend(child_edges)

    return nodes, edges


# ======================
# TASK IMPLEMENTATIONS
# ======================

def task_extract_audio_and_transcript(input_data: Dict[str, Any]) -> Dict[str, Any]:
    import subprocess
    video_id = input_data['video_id']
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[ASR] Processing video_id={video_id}, file={video_file}")
    _report_progress(video_id, "task_extract_audio_and_transcript", 5)

    if not os.path.isfile(video_file):
        raise FileNotFoundError(f"Video file not found: {video_file}")

    # --- Extract audio using ffmpeg (robust, no pydub dependency) ---
    wav_file = os.path.join(settings.MEDIA_AUDIO_DIR, f"{video_id}.wav")
    os.makedirs(os.path.dirname(wav_file), exist_ok=True)
    _report_progress(video_id, "task_extract_audio_and_transcript", 10)

    # Check if video has an audio stream
    probe_cmd = [
        "ffprobe", "-v", "quiet", "-select_streams", "a",
        "-show_entries", "stream=codec_type", "-of", "csv=p=0",
        video_file,
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
    has_audio = bool(probe_result.stdout.strip())

    if not has_audio:
        raise RuntimeError(
            f"Video file has no audio stream: {video_file}. "
            "ASR requires an audio track. Please upload a video with audio."
        )

    # Extract audio to WAV (16kHz mono)
    extract_cmd = [
        "ffmpeg", "-y", "-i", video_file,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        wav_file,
    ]
    logger.info(f"[ASR] Extracting audio: {' '.join(extract_cmd)}")
    _report_progress(video_id, "task_extract_audio_and_transcript", 20)
    result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr[:500]}")

    if not os.path.isfile(wav_file) or os.path.getsize(wav_file) == 0:
        raise RuntimeError(f"Audio extraction produced empty file: {wav_file}")
    logger.info(f"[ASR] Audio extracted: {wav_file} ({os.path.getsize(wav_file)} bytes)")
    _report_progress(video_id, "task_extract_audio_and_transcript", 40)

    # --- Upload to Tencent COS ---
    from qcloud_cos import CosConfig, CosS3Client
    from api.models import SystemConfig
    # Read COS credentials: SystemConfig > env vars
    cos_region = SystemConfig.get('cos_region') or os.environ.get('COS_REGION', '')
    cos_id = SystemConfig.get('cos_secret_id') or os.environ.get('COS_SECRECT_ID', '')
    cos_key_env = SystemConfig.get('cos_secret_key') or os.environ.get('COS_SECRECT_KEY', '')
    cos_bucket = SystemConfig.get('cos_bucket') or os.environ.get('COS_BUCKET', '')
    if not all([cos_region, cos_id, cos_key_env, cos_bucket]):
        raise RuntimeError(
            "COS credentials not configured. Set them in Settings page or "
            "via env vars: COS_REGION, COS_SECRECT_ID, COS_SECRECT_KEY, COS_BUCKET"
        )

    config = CosConfig(Region=cos_region, SecretId=cos_id, SecretKey=cos_key_env)
    client = CosS3Client(config)
    cos_key = f'audio/{video_id}.wav'
    logger.info(f"[ASR] Uploading to COS: bucket={cos_bucket}, key={cos_key}")
    client.upload_file(Bucket=cos_bucket, LocalFilePath=wav_file, Key=cos_key)
    signed_url = client.get_presigned_url(Method='GET', Bucket=cos_bucket, Key=cos_key, Expired=3600)
    logger.info(f"[ASR] COS upload complete, signed_url length={len(signed_url)}")
    _report_progress(video_id, "task_extract_audio_and_transcript", 60)

    # --- ASR transcription via DashScope ---
    from api.models import SystemConfig as _SC
    asr_api_key = _SC.get('dashscope_api_key') or os.environ.get('DASHSCOPE_API_KEY', '')
    asr_client = DashScopeASRClient(region="beijing", api_key=asr_api_key or None)
    logger.info(f"[ASR] Submitting to DashScope ASR...")
    _report_progress(video_id, "task_extract_audio_and_transcript", 70)
    transcript = asr_client.transcribe_audio(file_url=signed_url, language="en", timeout=600.0)

    # Log ASR result structure for debugging
    logger.info(
        f"[ASR] Transcript received: "
        f"transcripts={len(transcript.get('transcripts', []))}, "
        f"keys={list(transcript.keys())}"
    )
    _report_progress(video_id, "task_extract_audio_and_transcript", 90)

    save_transcript(video_id, transcript)
    logger.info(f"[ASR] Transcript saved for video {video_id}")
    return {"video_id": video_id, "file": input_data['file'], "cos_audio_url": signed_url}


def task_hls_streaming(input_data: Dict[str, Any]) -> Dict[str, Any]:
    video_id = input_data['video_id']
    video_file = get_local_file_path(input_data['file'])
    _report_progress(video_id, "task_hls_streaming", 10)
    generate_hls_renditions(input_video_path=video_file, video_id=video_id, output_root=settings.MEDIA_STREAMS_DIR)
    _report_progress(video_id, "task_hls_streaming", 80)
    path = generate_master_playlist(video_id=video_id, output_root=settings.MEDIA_STREAMS_DIR, output_filename="master-stream.m3u8")
    _report_progress(video_id, "task_hls_streaming", 100)
    return {"video_id": video_id, "master_m3u8_path": path}


def task_ssim_move_detection(input_data: Dict[str, Any]) -> Dict[str, Any]:
    video_id = input_data['video_id']
    video_file = get_local_file_path(input_data['file'])
    _report_progress(video_id, "task_ssim_move_detection", 5)

    def progress_callback(pct):
        _report_progress(video_id, "task_ssim_move_detection", pct)

    changes = detect_slide_changes_multithreaded(
        video_path=video_file, ssim_threshold=0.7, min_interval_sec=5.0,
        resize_width=240, sampling_fps=10.0, num_workers=16,
        progress_callback=progress_callback,
    )
    return {"video_id": video_id, "file": input_data['file'], "changes": changes}


def task_generate_thumbnails(input_data: Dict[str, Any]) -> Dict[str, Any]:
    video_id = input_data['video_id']
    video_file = get_local_file_path(input_data['file'])
    frames = input_data.get('changes', [])
    _report_progress(video_id, "task_generate_thumbnails", 5)

    # Process thumbnails with progress reporting
    total_frames = len(frames) if frames else 0
    if total_frames == 0:
        return {"video_id": video_id, "file": input_data['file'],
                "changes": [], "thumbnail_count": 0}

    # Process in batches and report progress
    from api.utils import generate_thumbnails_for_video
    thumbnails = []
    batch_size = max(1, total_frames // 10)  # Report ~10 times

    for i in range(0, total_frames, batch_size):
        batch_frames = frames[i:i + batch_size]
        batch_thumbs = generate_thumbnails_for_video(
            video_file=video_file, time_seconds=batch_frames, width=200, output_dir=settings.MEDIA_THUMBNAILS_DIR
        )
        thumbnails.extend(batch_thumbs)
        progress_pct = min(90, int((len(thumbnails) / total_frames) * 100))
        _report_progress(video_id, "task_generate_thumbnails", progress_pct)

    count = update_thumbnails_for_video(video_id, thumbnails)
    _report_progress(video_id, "task_generate_thumbnails", 95)

    # Set first thumbnail as video cover
    first_thumb = Thumbnail.objects.filter(video_id=video_id).order_by('time_second').first()
    if first_thumb and first_thumb.image:
        video = Video.objects.get(id=video_id)
        video.cover = first_thumb.image.url
        video.save(update_fields=['cover'])
        logger.info(f"[Thumbnails] Set cover for video {video_id}: {first_thumb.image.url}")

    return {"video_id": video_id, "file": input_data['file'],
            "changes": input_data.get('changes', []), "thumbnail_count": count}


def task_hybrid_chunking(input_data: Dict[str, Any]) -> Dict[str, Any]:
    video_id = input_data['video_id']
    slide_changes = input_data.get('changes', [])
    video = Video.objects.get(id=video_id)
    duration = video.duration
    if duration <= 0:
        if slide_changes:
            duration = max(slide_changes) + 60.0
        else:
            last = TranscriptSentence.objects.filter(
                video_transcript__video_id=video_id
            ).order_by('-end_time').first()
            duration = (last.end_time / 1000.0 + 10.0) if last else 3600.0

    asr = _get_transcript_as_asr_dict(video_id)
    all_sentences = []
    for tr in asr.get("transcripts", []):
        all_sentences.extend(tr.get("sentences", []))

    chunks = hybrid_chunk(
        slide_change_times=slide_changes, asr_transcript=asr,
        video_duration_sec=duration, min_chunk_duration=30.0,
        silence_gap_threshold=2.0, semantic_similarity_threshold=0.5,
        use_semantic_check=False,  # disabled for low-memory systems (8GB RAM)
    )

    VideoSection.objects.filter(video_id=video_id).delete()
    for i, (start, end) in enumerate(chunks):
        VideoSection.objects.create(
            video_id=video_id, title=f"Section {i + 1}",
            begin_time=start, end_time=end,
            transcript_text=_extract_transcript_for_range(all_sentences, start, end),
            thumbnail=_find_closest_thumbnail(video_id, start), order=i,
        )
    return {"video_id": video_id, "section_count": len(chunks)}


def task_fine_grained_knowledge(input_data: Dict[str, Any]) -> Dict[str, Any]:
    from api.llm_client import get_llm_client

    video_id = input_data['video_id']
    logger.info(f"[Fine-Grained Knowledge] Processing {video_id}")

    sections = VideoSection.objects.filter(video_id=video_id).order_by('order')
    if not sections.exists():
        return {"video_id": video_id, "knowledge_points_count": 0, "sections_processed": 0}

    llm = get_llm_client()
    KnowledgePoint.objects.filter(video_id=video_id).delete()
    total_kp, processed = 0, 0

    for section in sections:
        if not section.transcript_text or len(section.transcript_text.strip()) < 20:
            continue
        time_range = f"{_format_time(section.begin_time)} - {_format_time(section.end_time)}"
        transcript = section.transcript_text[:3000]
        if len(section.transcript_text) > 3000:
            transcript += "... [truncated]"

        prompt = FINE_GRAINED_EXTRACTION_PROMPT.format(
            section_title=section.title, time_range=time_range, transcript=transcript,
        )
        try:
            response = llm.chat(
                prompt=prompt,
                system_prompt="You are an expert educational content analyst. Respond with valid JSON only.",
                temperature=0.3, max_tokens=2048,
            )
            data = _parse_llm_json(response)
            new_title = data.get("section_title", "").strip()
            if new_title:
                section.title = new_title
                section.save(update_fields=['title'])

            for kp in data.get("points", []):
                title = kp.get("title", "").strip()
                summary = kp.get("summary", "").strip()
                if not title or not summary:
                    continue
                KnowledgePoint.objects.create(
                    section=section, video_id=video_id, title=title, summary=summary,
                    key_terms=kp.get("terms", []),
                    importance=min(max(float(kp.get("importance", 0.5)), 0.0), 1.0),
                )
                total_kp += 1
            processed += 1
            _report_progress(video_id, "task_fine_grained_knowledge", int((processed) / sections.count() * 100))
        except Exception as e:
            logger.error(f"[Fine-Grained] Section {section.order} failed: {e}")
            continue

    return {"video_id": video_id, "knowledge_points_count": total_kp, "sections_processed": processed}


def task_embed_knowledge(input_data: Dict[str, Any]) -> Dict[str, Any]:
    from api.vector_store import get_vector_store

    video_id = input_data['video_id']
    store = get_vector_store()
    store.delete_by_video(video_id)

    kps = KnowledgePoint.objects.filter(video_id=video_id).select_related('section')
    ids, texts, metas = [], [], []
    for kp in kps:
        embed_text = f"{kp.title}: {kp.summary}"
        if kp.key_terms:
            embed_text += f" (Key terms: {', '.join(kp.key_terms)})"
        ids.append(str(kp.id))
        texts.append(embed_text)
        metas.append({
            "video_id": video_id, "section_id": str(kp.section_id),
            "type": "knowledge_point", "title": kp.title,
            "begin_time": kp.section.begin_time, "end_time": kp.section.end_time,
            "importance": kp.importance,
        })
    _report_progress(video_id, "task_embed_knowledge", 30)
    emb_kp = store.upsert_batch(ids, texts, metas) if ids else 0

    sections = VideoSection.objects.filter(video_id=video_id).order_by('order')
    s_ids, s_texts, s_metas = [], [], []
    for s in sections:
        if not s.transcript_text or len(s.transcript_text.strip()) < 10:
            continue
        s_ids.append(f"section-{s.id}")
        s_texts.append(s.transcript_text[:2000])
        s_metas.append({
            "video_id": video_id, "section_id": str(s.id),
            "type": "section_transcript", "title": s.title,
            "begin_time": s.begin_time, "end_time": s.end_time,
        })
    _report_progress(video_id, "task_embed_knowledge", 60)
    emb_sec = store.upsert_batch(s_ids, s_texts, s_metas) if s_ids else 0

    for kp in kps:
        kp.embedding_id = str(kp.id)
    KnowledgePoint.objects.bulk_update(list(kps), ['embedding_id'])

    # Embed slide OCR text
    ocr_records = SlideOCR.objects.filter(video_id=video_id).order_by('time_second')
    ocr_ids, ocr_texts, ocr_metas = [], [], []
    for ocr in ocr_records:
        if not ocr.ocr_text or len(ocr.ocr_text.strip()) < 10:
            continue
        ocr_ids.append(f"slide-ocr-{ocr.id}")
        ocr_texts.append(ocr.ocr_text[:2000])
        # Find which section this slide belongs to (by time overlap)
        matching_section = VideoSection.objects.filter(
            video_id=video_id,
            begin_time__lte=ocr.time_second,
            end_time__gte=ocr.time_second,
        ).first()
        ocr_metas.append({
            "video_id": video_id,
            "section_id": str(matching_section.id) if matching_section else "",
            "type": "slide_ocr",
            "title": f"Slide @ {_format_time(ocr.time_second)}",
            "begin_time": ocr.time_second,
            "end_time": ocr.time_second,
        })
    _report_progress(video_id, "task_embed_knowledge", 90)
    emb_ocr = store.upsert_batch(ocr_ids, ocr_texts, ocr_metas) if ocr_ids else 0

    return {
        "video_id": video_id,
        "embedded_knowledge_points": emb_kp,
        "embedded_sections": emb_sec,
        "embedded_slide_ocr": emb_ocr,
    }


def task_coarse_grained_summary(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate all sections + knowledge points into a video-level summary.
    Saves a KnowledgeSummary record.
    """
    from api.llm_client import get_llm_client

    video_id = input_data['video_id']
    logger.info(f"[Coarse Summary] Processing {video_id}")

    video = Video.objects.get(id=video_id)
    sections = VideoSection.objects.filter(video_id=video_id).order_by('order')
    kps = KnowledgePoint.objects.filter(video_id=video_id).select_related('section')

    # Build sections text for the prompt
    sections_lines = []
    for s in sections:
        time_range = f"{_format_time(s.begin_time)}-{_format_time(s.end_time)}"
        section_kps = [kp for kp in kps if str(kp.section_id) == str(s.id)]
        kp_text = ""
        if section_kps:
            kp_bullets = [f"  - {kp.title}: {kp.summary}" for kp in section_kps]
            kp_text = "\n".join(kp_bullets)

        sections_lines.append(
            f"Section {s.order + 1}: {s.title} ({time_range})"
            + (f"\n{kp_text}" if kp_text else "")
        )

    sections_text = "\n\n".join(sections_lines)
    if len(sections_text) > 6000:
        sections_text = sections_text[:6000] + "\n... [truncated]"

    prompt = COARSE_SUMMARY_PROMPT.format(
        video_title=video.title, sections_text=sections_text,
    )

    llm = get_llm_client()
    try:
        response = llm.chat(
            prompt=prompt,
            system_prompt="You are an expert educational content analyst. Respond with valid JSON only.",
            temperature=0.3, max_tokens=2048,
        )
        data = _parse_llm_json(response)
    except Exception as e:
        logger.error(f"[Coarse Summary] LLM call failed: {e}")
        data = {
            "overview": f"Summary generation failed for video {video.title}.",
            "key_topics": [], "learning_objectives": [],
            "prerequisites": [], "difficulty_level": "unknown",
        }

    KnowledgeSummary.objects.update_or_create(
        video_id=video_id,
        defaults={
            "overview": data.get("overview", ""),
            "key_topics": data.get("key_topics", []),
            "learning_objectives": data.get("learning_objectives", []),
            "prerequisites": data.get("prerequisites", []),
            "difficulty_level": data.get("difficulty_level", ""),
        }
    )

    logger.info(f"[Coarse Summary] Complete for {video_id}")
    return {"video_id": video_id, "summary_created": True}


def task_generate_mindmap(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a hierarchical mindmap from sections + knowledge points.
    Saves tree_data + pre-computed React Flow nodes/edges.
    """
    from api.llm_client import get_llm_client

    video_id = input_data['video_id']
    logger.info(f"[Mindmap] Processing {video_id}")

    video = Video.objects.get(id=video_id)
    sections = VideoSection.objects.filter(video_id=video_id).order_by('order')
    kps = KnowledgePoint.objects.filter(video_id=video_id).select_related('section')

    # Build sections text
    sections_lines = []
    for s in sections:
        time_range = f"{_format_time(s.begin_time)}-{_format_time(s.end_time)}"
        section_kps = [kp for kp in kps if str(kp.section_id) == str(s.id)]
        kp_text = ""
        if section_kps:
            kp_bullets = [f"  - {kp.title}" + (f" ({', '.join(kp.key_terms[:3])})" if kp.key_terms else "")
                          for kp in section_kps]
            kp_text = "\n".join(kp_bullets)
        sections_lines.append(
            f"Section {s.order + 1}: {s.title} ({time_range})"
            + (f"\n{kp_text}" if kp_text else "")
        )

    sections_text = "\n\n".join(sections_lines)
    if len(sections_text) > 5000:
        sections_text = sections_text[:5000] + "\n... [truncated]"

    prompt = MINDMAP_PROMPT.format(
        video_title=video.title, sections_text=sections_text,
    )

    llm = get_llm_client()
    try:
        response = llm.chat(
            prompt=prompt,
            system_prompt="You are an expert educational content analyst. Respond with valid JSON only.",
            temperature=0.4, max_tokens=3000,
        )
        tree_data = _parse_llm_json(response)
    except Exception as e:
        logger.error(f"[Mindmap] LLM call failed: {e}")
        # Fallback: build a simple tree from sections
        tree_data = {
            "id": "root",
            "label": video.title,
            "children": [
                {
                    "id": f"section-{s.order}",
                    "label": s.title or f"Section {s.order + 1}",
                    "children": [
                        {"id": str(kp.id)[:8], "label": kp.title, "children": []}
                        for kp in kps if str(kp.section_id) == str(s.id)
                    ]
                }
                for s in sections
            ]
        }

    # Convert tree to React Flow nodes + edges
    try:
        rf_nodes, rf_edges = _tree_to_react_flow(tree_data, x=400, y=0)
    except Exception as e:
        logger.error(f"[Mindmap] React Flow conversion failed: {e}")
        rf_nodes, rf_edges = [], []

    KnowledgeMindmap.objects.update_or_create(
        video_id=video_id,
        defaults={
            "tree_data": tree_data,
            "react_flow_nodes": rf_nodes,
            "react_flow_edges": rf_edges,
        }
    )

    logger.info(f"[Mindmap] Complete: {len(rf_nodes)} nodes, {len(rf_edges)} edges for {video_id}")
    return {
        "video_id": video_id,
        "mindmap_nodes": len(rf_nodes),
        "mindmap_edges": len(rf_edges),
    }



def task_slides_ocr(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    OCR slide thumbnails using Qwen2.5-VL-72B-Instruct vision-language model.

    For each thumbnail of the video, sends the image to the VL model to extract
    all visible text content. Results are stored as SlideOCR records linked to
    each thumbnail, and will later be embedded into the vector store for RAG.
    """
    from api.llm_client import get_llm_client
    from django.conf import settings as django_settings

    video_id = input_data['video_id']
    logger.info(f"[Slides OCR] Processing video_id={video_id}")

    thumbnails = Thumbnail.objects.filter(video_id=video_id).order_by('time_second')
    if not thumbnails.exists():
        logger.warning(f"[Slides OCR] No thumbnails found for video {video_id}")
        return {"video_id": video_id, "ocr_count": 0, "skipped": 0}

    # Delete existing OCR records for this video (idempotent re-run)
    SlideOCR.objects.filter(video_id=video_id).delete()

    llm = get_llm_client()
    ocr_count = 0
    skipped = 0

    for thumb in thumbnails:
        if not thumb.image:
            skipped += 1
            continue

        # Build the image URL — use absolute file path for local serving
        # DashScope VL API needs an accessible URL; for local files we use file:// or
        # construct the Django media URL. Since DashScope is a remote API, we need
        # to encode the image as a base64 data URI.
        try:
            # Use high-res image for OCR if available, otherwise fall back to low-res
            if thumb.image_high_res and os.path.isfile(thumb.image_high_res.path):
                image_path = thumb.image_high_res.path
                logger.debug(f"[Slides OCR] Using high-res image for slide @ {thumb.time_second}s")
            else:
                image_path = thumb.image.path
                logger.debug(f"[Slides OCR] Using low-res image for slide @ {thumb.time_second}s (high-res not available)")
            
            if not os.path.isfile(image_path):
                logger.warning(f"[Slides OCR] Image file not found: {image_path}")
                skipped += 1
                continue

            # Read image and encode as base64 data URI for the VL API
            import base64
            with open(image_path, 'rb') as img_file:
                img_data = img_file.read()
            # Determine MIME type from extension
            ext = os.path.splitext(image_path)[1].lower()
            mime_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
            mime_type = mime_map.get(ext, 'image/jpeg')
            b64_str = base64.b64encode(img_data).decode('utf-8')
            image_url = f"data:{mime_type};base64,{b64_str}"

            response = llm.chat_vl(
                prompt=SLIDE_OCR_PROMPT,
                image_urls=[image_url],
                system_prompt="You are an expert OCR system specialized in extracting text from lecture slides. Extract all visible text accurately.",
                temperature=0.1,
                max_tokens=2048,
            )

            ocr_text = response.strip()
            if not ocr_text or ocr_text == "[NO TEXT CONTENT]":
                logger.info(f"[Slides OCR] No text content in slide @ {thumb.time_second}s")
                skipped += 1
                continue

            SlideOCR.objects.create(
                thumbnail=thumb,
                video_id=video_id,
                ocr_text=ocr_text,
                time_second=thumb.time_second,
            )
            ocr_count += 1
            total_thumbs = thumbnails.count()
            logger.info(
                f"[Slides OCR] Extracted {len(ocr_text)} chars from slide @ {thumb.time_second}s "
                f"({ocr_count}/{total_thumbs})"
            )
            _report_progress(video_id, "task_slides_ocr", int((ocr_count + skipped) / total_thumbs * 100))

        except Exception as e:
            logger.error(f"[Slides OCR] Failed for slide @ {thumb.time_second}s: {e}")
            skipped += 1
            continue

    logger.info(f"[Slides OCR] Complete: {ocr_count} slides OCR'd, {skipped} skipped for video {video_id}")
    return {"video_id": video_id, "ocr_count": ocr_count, "skipped": skipped}


# ======================
# TASK REGISTRY
# ======================
TASK_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "task_extract_audio_and_transcript": task_extract_audio_and_transcript,
    "task_hls_streaming": task_hls_streaming,
    "task_ssim_move_detection": task_ssim_move_detection,
    "task_generate_thumbnails": task_generate_thumbnails,
    "task_slides_ocr": task_slides_ocr,
    "task_hybrid_chunking": task_hybrid_chunking,
    "task_fine_grained_knowledge": task_fine_grained_knowledge,
    "task_embed_knowledge": task_embed_knowledge,
    "task_coarse_grained_summary": task_coarse_grained_summary,
    "task_generate_mindmap": task_generate_mindmap,
}

def get_task_function(func_name: str) -> Callable:
    if func_name not in TASK_REGISTRY:
        raise ValueError(f"Unknown task: {func_name}. Known: {list(TASK_REGISTRY.keys())}")
    return TASK_REGISTRY[func_name]
