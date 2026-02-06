# myapp/tasks.py
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
from api.models import  Video, Thumbnail, VideoTranscript, TranscriptSentence

from api.dashscope_asr import DashScopeASRClient
from api.lecture_video_slides_chunker import detect_slide_changes_multithreaded
from api.utils import generate_master_playlist, generate_hls_renditions

logger = logging.getLogger('polyu-video')



def save_transcript(video_id: str, data: Dict[str, Any]) -> None:
    """
    Save the ASR result data into the Django database.

    Args:
        data (Dict[str, Any]): ASR result as a dictionary.

    Raises:
        ValueError: If required fields are missing.
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
        TranscriptSentence.objects.filter(video_transcript=video_transcript, channel_id=channel_id).delete()

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
    
    Args:
        video_id (str): UUID string of the video
        thumbnail_data (list[dict]): List like:
            [
                {
                    'image_id': '309ef35e-...',
                    'time_second': 446.4,
                    'image': './media/thumbnails/309ef35e-....jpg'
                },
                ...
            ]
    """
    # Validate and get video
    try:
        video_uuid = uuid.UUID(video_id)
        video = Video.objects.get(id=video_uuid)
    except (ValueError, Video.DoesNotExist) as e:
        raise ValueError(f"Invalid or missing video ID: {video_id}") from e

    # Delete existing thumbnails (cleanup old files too)
    old_thumbnails = Thumbnail.objects.filter(video=video)
    for thumb in old_thumbnails:
        if thumb.image and os.path.isfile(thumb.image.path):
            os.remove(thumb.image.path)  # Optional: delete old image file
    old_thumbnails.delete()

    # Create new thumbnails
    created_count = 0
    for item in thumbnail_data:
        try:
            # Validate fields
            img_id = uuid.UUID(item['image_id'])
            time_sec = float(item['time_second'])
            img_path = item['image']

            if not os.path.isfile(img_path):
                print(f"⚠️ Image not found: {img_path}")
                continue

            # Create new Thumbnail instance
            thumb = Thumbnail(
                id=img_id,
                video=video,
                time_second=time_sec
            )

            # Open and assign file to ImageField
            with open(img_path, 'rb') as f:
                # Save under correct upload path (e.g., 'thumbnails/filename.jpg')
                filename = os.path.basename(img_path)
                thumb.image.save(filename, File(f), save=True)

            created_count += 1

        except (KeyError, ValueError, TypeError, OSError) as e:
            print(f"❌ Skipping invalid thumbnail entry {item}: {e}")
            continue

    return created_count
    
    
# ======================
# TASK IMPLEMENTATIONS
# ======================

def task_extract_audio_and_transcript(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    STUB: Extract audio, upload video to Tencent COS, transcribe with Qwen-ASR.
    
    Input: {"video_id": "uuid-str", "file" : "file relative path"}
    Output: {
        "video_id": "uuid-str",
        "file" : "video/video.mp4",
        "cos_audio_url": "https://...",
    }
    """
    # 1. Fetch Video instance using input_data['video_id']
    video_id = input_data['video_id']
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[ASR Task] Processing video {video_id}")
    
    # 2. Use ffmpeg to extract audio
    logger.info("processing audio done.")
    from pydub import AudioSegment
    # Requires FFmpeg installed system-wide
    wav_file = os.path.join(settings.MEDIA_ROOT, "audio", f"{video_id}.wav")
    logger.info(f"Begin process audio from {video_file} to {wav_file}")
    audio = AudioSegment.from_file(video_file, format="mp4")
    audio = audio.set_frame_rate(16000).set_channels(1)  # 16kHz mono
    audio.export(wav_file, format="wav")
    logger.info("End process audio.")

    # 3. Upload original video to Tencent COS
    logger.info("Begin upload audio.")
    from qcloud_cos import CosConfig, CosS3Client
    # Configure (get from https://console.cloud.tencent.com/cam/capi)
    config = CosConfig(Region=os.environ['COS_REGION'], SecretId=os.environ['COS_SECRECT_ID'], SecretKey=os.environ['COS_SECRECT_KEY'])
    client = CosS3Client(config)
    bucket = os.environ['COS_BUCKET']
    cos_key = f'audio/{video_id}.wav'
    response = client.upload_file(
        Bucket=bucket,
        LocalFilePath=wav_file,
        Key=cos_key
    )
    # Get presigned URL for external use (e.g., DashScope)
    signed_url = client.get_presigned_url(
        Method='GET',
        Bucket=bucket,
        Key=cos_key,
        Expired=3600  # seconds
    )
    logger.info(f"COS uploaded audio URL: {signed_url}")
    logger.info("End upload audio.")

    # 4. Call Qwen-ASR API with audio URL
    logger.info("Begin process audio ASR.")
    client = DashScopeASRClient(region="beijing")
    transcript = client.transcribe_audio(
        file_url=signed_url,
        language="en",
        timeout=600.0
    )
    save_transcript(video_id, transcript)

    logger.info("End process audio ASR.")
    return {
        "video_id": input_data["video_id"],
        "file" : input_data['file'],
        "cos_audio_url": signed_url,
    }


def task_hls_streaming(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    STUB: Generate HLS with different resolution for online streaming
    
    Input: {"video_id": "uuid-str", "file" : "file relative path"}
    
    Output: {
        "video_id": "uuid-str",
        "file" : "video/video.mp4",
        "changes": [10.22, 34.32, ...],
    }
    """
    video_id = input_data.get('video_id')
    video_file = get_local_file_path(input_data['file'])
    logger.info(f"[HLS Task] Generate HLS files, video_id: {video_id}")
    # 1. Generate different resolutions
    generate_hls_renditions(
        input_video_path=video_file,
        video_id=video_id,
        output_root="./media/streams"
    )
    # 2. Generate master m3u8
    master_m3u8_path = generate_master_playlist(
        video_id=video_id,
        output_root="./media/streams",
        output_filename="master-stream.m3u8"
    )

    logger.info(f"[HLS Task] Complete generating HLS files, video_id: {video_id}")
    return {
        "video_id": input_data["video_id"],
        "master_m3u8_path" : master_m3u8_path
    }


def task_ssim_move_detection(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    STUB: Use SSIM algorithm to detect video frame change
    
    Input: {"video_id": "uuid-str", "file" : "file relative path"}
    
    Output: {
        "video_id": "uuid-str",
        "file" : "video/video.mp4",
        "changes": [10.22, 34.32, ...],
    }
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
        "file" : input_data['file'],
        "changes": changes,
    }


def task_generate_thumbnails(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    STUB: Generate video thumbnails using video data.
    
    Input: {"video_id": "uuid-str", "file" : "file relative path", "changes": [10.22, 34.32, ...]}
    
    Output: {
        "video_id": "uuid-str",
        "file" : "video/video.mp4"
        "thumbnail_count": 3
    }
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
        "file" : input_data['file'],
        "thumbnail_count": count
    }
    

def task_generate_summary(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    STUB: Generate AI summary using transcript and metadata.
    
    Input: Output from task_generate_thumbnails (MUST contain video_id)
    Output: {
        "video_id": "uuid-str",
        "summary": "Concise summary text...",
        "keywords": ["keyword1", "keyword2"]
    }
    """
    logger.info(f"[Summary Task] Processing video {input_data.get('video_id')}")
    # REAL IMPLEMENTATION WOULD:
    # 1. Fetch transcript from DB or input chain
    # 2. Call LLM API (Qwen, etc.) with transcript
    # 3. Parse and return structured summary
    
    return {
        "video_id": input_data["video_id"],
        "summary": f"AI-generated summary for video {input_data['video_id']} created at {timezone.now().isoformat()}",
        "keywords": ["video", "summary", "ai", "processing"]
    }

# ======================
# TASK REGISTRY
# ======================
TASK_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "task_extract_audio_and_transcript": task_extract_audio_and_transcript,
    "task_hls_streaming" : task_hls_streaming,
    "task_ssim_move_detection" : task_ssim_move_detection,
    "task_generate_thumbnails": task_generate_thumbnails,
    "task_generate_summary": task_generate_summary,
}

def get_task_function(func_name: str) -> Callable:
    """Safely retrieve task function from registry"""
    if func_name not in TASK_REGISTRY:
        raise ValueError(f"Unknown task function: {func_name}. Registered: {list(TASK_REGISTRY.keys())}")
    return TASK_REGISTRY[func_name]