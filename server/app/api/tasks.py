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
from typing import Dict, Any, Callable
from django.utils import timezone
import sys
import requests
import json
import os
import time
import uuid
from django.core.files import File
from django.conf import settings
from api.utils import generate_thumbnails_for_video, get_local_file_path
from api.models import Video, Thumbnail, VideoTranscript, TranscriptSentence, VideoSection

from api.dashscope_asr import DashScopeASRClient
from api.lecture_video_slides_chunker import detect_slide_changes_multithreaded
from api.lecture_video_hybrid_chunker import hybrid_chunk
from api.utils import generate_master_playlist, generate_hls_renditions

logger = logging.getLogger('polyu-video')


def save_transcript(video_id: str, data: Dict[str, Any]) -> None:
    """
    Save the ASR result data into the Django database.
    """
    # Create or update the VideoTranscript
    video_transcript, created = VideoTranscript.objects.update_or_create(
        video_id=video_id,
        defaults={
            "file_url": data.get("file_url", ""),
            "format": data.get("audio_info", {}).get("format", ""),
            "sample_rate": data.get("audio_info", {}).get("sample_rate", 0),
        }
    )

    # Process each transcript entry
    for transcript in data.get("transcripts", []):
        channel_id = transcript.get("channel_id", 0)

        # Delete existing sentences for this channel
        TranscriptSentence.objects.filter(
            video_transcript=video_transcript, channel_id=channel_id
        ).delete()

        # Add new sentences
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
    """
    Replace all thumbnails for a video with new ones from provided data.
    """
    try:
        video_uuid = uuid.UUID(video_id)
        video = Video.objects.get(id=video_uuid)
    except (ValueError, Video.DoesNotExist) as e:
        raise ValueError(f"Invalid or missing video ID: {video_id}") from e

    # Delete existing thumbnails
    old_thumbnails = Thumbnail.objects.filter(video=video)
    for thumb in old_thumbnails:
        if thumb.image and os.path.isfile(thumb.image.path):
            os.remove(thumb.image.path)
    old_thumbnails.delete()

    # Create new thumbnails
    created_count = 0
    for item in thumbnail_data:
        try:
            img_id = uuid.UUID(item['image_id'])
            time_sec = float(item['time_second'])
            img_path = item['image']

            if not os.path.isfile(img_path):
                logger.warning(f"Image not found: {img_path}")
                continue

            thumb = Thumbnail(
                id=img_id,
                video=video,
                time_second=time_sec
            )

            with open(img_path, 'rb') as f:
                filename = os.path.basename(img_path)
                thumb.image.save(filename, File(f), save=True)

            created_count += 1

        except (KeyError, ValueError, TypeError, OSError) as e:
            logger.warning(f"Skipping invalid thumbnail entry {item}: {e}")
            continue

    return created_count


def _get_transcript_as_asr_dict(video_id: str) -> Dict[str, Any]:
    """
    Fetch transcript from database and reconstruct the ASR dict format
    that the hybrid chunker expects.
    """
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
        "audio_info": {
            "format": vt.format,
            "sample_rate": vt.sample_rate,
        },
        "transcripts": [
            {
                "channel_id": 0,
                "sentences": sentence_list,
            }
        ],
    }


def _extract_transcript_for_range(
    sentences: list,
    begin_sec: float,
    end_sec: float,
) -> str:
    """
    Extract concatenated transcript text for a given time range.
    Sentences are in ASR dict format with begin_time/end_time in milliseconds.
    """
    texts = []
    begin_ms = begin_sec * 1000
    end_ms = end_sec * 1000
    for s in sentences:
        s_begin = s.get("begin_time", 0)
        s_end = s.get("end_time", 0)
        # Include sentence if it overlaps with the range
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


# ======================
# TASK IMPLEMENTATIONS
# ======================

def task_extract_audio_and_transcript(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract audio, upload to Tencent COS, transcribe with Qwen-ASR.

    Input: {"video_id": "uuid-str", "file": "file relative path"}
    Output: {"video_id": "uuid-str", "file": "...", "cos_audio_url": "https://..."}
    """
    video_id = input_data['video_id']
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[ASR Task] Processing video {video_id}")

    # Extract audio
    from pydub import AudioSegment
    wav_file = os.path.join(settings.MEDIA_ROOT, "audio", f"{video_id}.wav")
    os.makedirs(os.path.dirname(wav_file), exist_ok=True)
    logger.info(f"Begin process audio from {video_file} to {wav_file}")
    audio = AudioSegment.from_file(video_file, format="mp4")
    audio = audio.set_frame_rate(16000).set_channels(1)
    audio.export(wav_file, format="wav")
    logger.info("End process audio.")

    # Upload to Tencent COS
    logger.info("Begin upload audio.")
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
    logger.info(f"COS uploaded audio URL: {signed_url}")
    logger.info("End upload audio.")

    # Call Qwen-ASR
    logger.info("Begin process audio ASR.")
    asr_client = DashScopeASRClient(region="beijing")
    transcript = asr_client.transcribe_audio(
        file_url=signed_url, language="en", timeout=600.0
    )
    save_transcript(video_id, transcript)
    logger.info("End process audio ASR.")

    return {
        "video_id": input_data["video_id"],
        "file": input_data['file'],
        "cos_audio_url": signed_url,
    }


def task_hls_streaming(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate HLS multi-resolution streaming files.

    Input: {"video_id": "uuid-str", "file": "file relative path"}
    Output: {"video_id": "uuid-str", "master_m3u8_path": "..."}
    """
    video_id = input_data.get('video_id')
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[HLS Task] Generate HLS files, video_id: {video_id}")

    generate_hls_renditions(
        input_video_path=video_file,
        video_id=video_id,
        output_root="./media/streams"
    )
    master_m3u8_path = generate_master_playlist(
        video_id=video_id,
        output_root="./media/streams",
        output_filename="master-stream.m3u8"
    )

    logger.info(f"[HLS Task] Complete generating HLS files, video_id: {video_id}")
    return {
        "video_id": input_data["video_id"],
        "master_m3u8_path": master_m3u8_path,
    }


def task_ssim_move_detection(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use SSIM algorithm to detect video frame changes (slide transitions).

    Input: {"video_id": "uuid-str", "file": "file relative path"}
    Output: {"video_id": "uuid-str", "file": "...", "changes": [10.22, 34.32, ...]}
    """
    video_id = input_data.get('video_id')
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[SSIM Task] Processing SSIM frame change detection, video_id: {video_id}")

    changes = detect_slide_changes_multithreaded(
        video_path=video_file,
        ssim_threshold=0.7,
        min_interval_sec=5.0,
        resize_width=240,
        sampling_fps=10.0,
        num_workers=16,
    )
    logger.info(f"[SSIM Task] Complete SSIM frame change detection, video_id: {video_id}")
    return {
        "video_id": input_data["video_id"],
        "file": input_data['file'],
        "changes": changes,
    }


def task_generate_thumbnails(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate video thumbnails at detected slide change timestamps.

    Input: {"video_id": "uuid-str", "file": "...", "changes": [...]}
    Output: {"video_id": "uuid-str", "file": "...", "changes": [...], "thumbnail_count": N}
    """
    video_id = input_data.get('video_id')
    video_file = get_local_file_path(input_data['file'])
    frames = input_data.get('changes')
    logger.info(f"[Thumbnails Task] Processing thumbnail generation, video id: {video_id}")

    thumbnails = generate_thumbnails_for_video(
        video_file=video_file,
        time_seconds=frames,
        width=200,
        output_dir="./media/thumbnails"
    )
    for thumb in thumbnails:
        logger.debug(f'Thumbnail: {thumb}')
    count = update_thumbnails_for_video(video_id, thumbnails)

    logger.info(f"[Thumbnails Task] Complete thumbnail generation, video id: {video_id}")
    return {
        "video_id": input_data["video_id"],
        "file": input_data['file'],
        "changes": input_data.get('changes', []),
        "thumbnail_count": count,
    }


def task_hybrid_chunking(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Combine SSIM slide changes + ASR transcript to produce intelligent
    video sections using the hybrid chunker.

    This task reads the ASR transcript from the database (saved by the ASR task)
    and uses slide change timestamps from the predecessor task chain.

    Input: {"video_id": "uuid-str", "file": "...", "changes": [...], ...}
    Output: {"video_id": "uuid-str", "section_count": N}
    """
    video_id = input_data['video_id']
    slide_changes = input_data.get('changes', [])
    logger.info(f"[Hybrid Chunking Task] Processing video {video_id}")

    # Get video duration
    video = Video.objects.get(id=video_id)
    video_duration = video.duration

    # If duration is 0 (not set), try to estimate from slide changes or transcript
    if video_duration <= 0:
        if slide_changes:
            video_duration = max(slide_changes) + 60.0  # rough estimate
        else:
            # Try from transcript
            last_sentence = TranscriptSentence.objects.filter(
                video_transcript__video_id=video_id
            ).order_by('-end_time').first()
            if last_sentence:
                video_duration = last_sentence.end_time / 1000.0 + 10.0
            else:
                video_duration = 3600.0  # fallback: 1 hour
        logger.warning(
            f"[Hybrid Chunking Task] Video duration was 0, estimated as {video_duration:.1f}s"
        )

    # Get ASR transcript from DB in the format the chunker expects
    asr_transcript = _get_transcript_as_asr_dict(video_id)
    all_sentences = []
    for tr in asr_transcript.get("transcripts", []):
        all_sentences.extend(tr.get("sentences", []))

    logger.info(
        f"[Hybrid Chunking Task] Inputs: {len(slide_changes)} slide changes, "
        f"{len(all_sentences)} transcript sentences, "
        f"{video_duration:.1f}s duration"
    )

    # Run hybrid chunker
    chunks = hybrid_chunk(
        slide_change_times=slide_changes,
        asr_transcript=asr_transcript,
        video_duration_sec=video_duration,
        min_chunk_duration=30.0,
        silence_gap_threshold=2.0,
        semantic_similarity_threshold=0.5,
        use_semantic_check=True,
    )

    # Clear existing sections for this video
    VideoSection.objects.filter(video_id=video_id).delete()

    # Save VideoSection records
    for i, (start, end) in enumerate(chunks):
        transcript_text = _extract_transcript_for_range(all_sentences, start, end)
        thumbnail = _find_closest_thumbnail(video_id, start)

        VideoSection.objects.create(
            video_id=video_id,
            title=f"Section {i + 1}",
            begin_time=start,
            end_time=end,
            transcript_text=transcript_text,
            thumbnail=thumbnail,
            order=i,
        )

    logger.info(
        f"[Hybrid Chunking Task] Complete: created {len(chunks)} sections for video {video_id}"
    )

    return {
        "video_id": video_id,
        "section_count": len(chunks),
    }


def task_generate_summary(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate AI summary using transcript and metadata.

    Input: Output from previous task (MUST contain video_id)
    Output: {"video_id": "uuid-str", "summary": "...", "keywords": [...]}
    """
    logger.info(f"[Summary Task] Processing video {input_data.get('video_id')}")
    # STUB: Will be replaced with real LLM call in Phase 2
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
