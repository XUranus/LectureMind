from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.db import connection
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from typing import Any, Dict

import logging
import json
import os

from .models import (
    Video,
    Thumbnail,
    VideoTranscript,
    VideoSection,
    KnowledgePoint,
    Episode,
    AsyncTaskItem,
)
from .serializers import (
    VideoSerializer,
    ThumbnailSerializer,
    VideoUploadSerializer,
    VideoTranscriptSerializer,
    VideoSectionSerializer,
    KnowledgePointSerializer,
    SectionWithKnowledgeSerializer,
    EpisodeSerializer,
    AsyncTaskItemSerializer,
    TriggerTaskSerializer,
)

logger = logging.getLogger('polyu-video')


# ======================
# HEALTH CHECK
# ======================

@api_view(['GET'])
def health_check(request):
    """Server health check endpoint."""
    db_ok = True
    try:
        connection.ensure_connection()
    except Exception:
        db_ok = False

    storage_ok = os.path.isdir(settings.MEDIA_ROOT)
    all_ok = db_ok and storage_ok

    return Response({
        "ok": all_ok,
        "ready": all_ok,
        "db": "connected" if db_ok else "error",
        "storage": settings.MEDIA_ROOT if storage_ok else "error",
        "cache": "none",
        "logger": "polyu-video",
    }, status=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE)


# ======================
# VIDEO VIEWS
# ======================

class VideoListView(generics.ListAPIView):
    """List all videos."""
    queryset = Video.objects.all()
    serializer_class = VideoSerializer


class VideoDetailView(generics.RetrieveAPIView):
    """Retrieve a specific video by ID."""
    queryset = Video.objects.all()
    serializer_class = VideoSerializer


class VideoDeleteView(generics.DestroyAPIView):
    """DELETE /videos/<uuid:pk>/ — Delete a video."""
    queryset = Video.objects.all()
    serializer_class = VideoSerializer


class VideoUpdateView(generics.UpdateAPIView):
    """Update a video by its `id` field (not the default `pk`)."""
    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    lookup_field = 'id'


class ThumbnailListView(generics.ListAPIView):
    """List thumbnails associated with a specific video."""
    serializer_class = ThumbnailSerializer

    def get_queryset(self):
        video_id = self.kwargs['video_id']
        return Thumbnail.objects.filter(video_id=video_id).order_by('time_second')

    def get_serializer_context(self) -> Dict[str, Any]:
        return {'request': self.request}


class VideoUploadView(generics.CreateAPIView):
    """Upload a new video file."""
    queryset = Video.objects.all()
    serializer_class = VideoUploadSerializer
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            os.makedirs(os.path.join(settings.MEDIA_ROOT, "videos"), exist_ok=True)
            serializer.save()
            logger.info("Video uploaded successfully: %s", serializer.data.get('id'))
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning("Video upload failed with errors: %s", serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VideoTaskTriggerView(generics.GenericAPIView):
    """
    POST /api/videos/process/
    Triggers an asynchronous processing pipeline for an existing video.
    """
    serializer_class = TriggerTaskSerializer

    def post(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("Invalid data in task trigger request: %s", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        video_id = serializer.validated_data['id']
        video = get_object_or_404(Video, id=video_id)
        logger.info("Processing task triggered for video ID: %s", video.id)

        if video.async_tasks.filter(status__in=['pending', 'running']).exists():
            logger.info("Task chain already active for video ID: %s", video.id)
            return Response(
                {"error": "Tasks already exist for this video (pending or running)."},
                status=status.HTTP_409_CONFLICT
            )

        try:
            self._create_processing_chain(video)
            logger.info("Async task chain successfully created for video ID: %s", video.id)
        except Exception as e:
            logger.exception("Failed to create task chain for video ID %s: %s", video.id, str(e))
            return Response(
                {"error": "Task initialization failed", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _create_processing_chain(self, video: Video) -> None:
        """
        Creates a directed acyclic graph of async tasks for video processing.

        Task DAG:
          Task 1 (ASR), Task 2 (HLS), Task 3 (SSIM) — parallel, no deps
          Task 4 (Thumbnails) — depends on Task 3
          Task 5 (Hybrid Chunking) — depends on Task 4 (reads ASR from DB)
          Task 6 (Fine-Grained Knowledge) — depends on Task 5
          Task 7 (Embed Knowledge) — depends on Task 6
          Task 8 (Summary) — depends on Task 7
        """
        # Task 1: ASR (parallel)
        task1 = AsyncTaskItem.objects.create(
            video=video,
            title="Extract audio & generate transcript",
            description="Extract audio track, upload to COS, transcribe with Qwen-ASR",
            func_name="task_extract_audio_and_transcript",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None
        )

        # Task 2: HLS (parallel)
        task2 = AsyncTaskItem.objects.create(
            video=video,
            title="Generate HLS",
            description="Generate HLS with multiple resolutions for online streaming",
            func_name="task_hls_streaming",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None
        )

        # Task 3: SSIM (parallel)
        task3 = AsyncTaskItem.objects.create(
            video=video,
            title="SSIM Motion Detection",
            description="Use SSIM algorithm to detect significant frame changes",
            func_name="task_ssim_move_detection",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None
        )

        # Task 4: Thumbnails (depends on SSIM)
        task4 = AsyncTaskItem.objects.create(
            video=video,
            title="Generate video thumbnails",
            description="Create preview thumbnails using processed video data",
            func_name="task_generate_thumbnails",
            param=json.dumps({"video_id": str(video.id)}),
            previous=task3.id
        )

        # Task 5: Hybrid Chunking (depends on Thumbnails)
        task5 = AsyncTaskItem.objects.create(
            video=video,
            title="Hybrid video chunking",
            description="Combine SSIM slide changes + ASR transcript for intelligent segmentation",
            func_name="task_hybrid_chunking",
            param=json.dumps({"video_id": str(video.id)}),
            previous=task4.id
        )

        # Task 6: Fine-Grained Knowledge Extraction (depends on Hybrid Chunking)
        task6 = AsyncTaskItem.objects.create(
            video=video,
            title="Extract knowledge points",
            description="Use LLM to extract structured knowledge points from each section",
            func_name="task_fine_grained_knowledge",
            param=json.dumps({"video_id": str(video.id)}),
            previous=task5.id
        )

        # Task 7: Embed Knowledge into Vector Store (depends on Knowledge Extraction)
        task7 = AsyncTaskItem.objects.create(
            video=video,
            title="Embed knowledge vectors",
            description="Generate embeddings for knowledge points and store in vector DB",
            func_name="task_embed_knowledge",
            param=json.dumps({"video_id": str(video.id)}),
            previous=task6.id
        )

        # Task 8: Summary (depends on Embedding)
        task8 = AsyncTaskItem.objects.create(
            video=video,
            title="Generate content summary",
            description="Create AI-generated summary using transcript and metadata",
            func_name="task_generate_summary",
            param=json.dumps({"video_id": str(video.id)}),
            previous=task7.id
        )

        logger.debug(
            "Created task chain: ASR(%s), HLS(%s), SSIM(%s) -> "
            "Thumbnails(%s) -> Chunking(%s) -> Knowledge(%s) -> "
            "Embed(%s) -> Summary(%s)",
            task1.id, task2.id, task3.id, task4.id,
            task5.id, task6.id, task7.id, task8.id
        )


# ======================
# TRANSCRIPT VIEWS
# ======================

class TranscriptDetailView(generics.GenericAPIView):
    """Retrieve the transcript for a specific video by video_id."""

    def get(self, request, video_id: str, format=None) -> Response:
        try:
            video_transcript = VideoTranscript.objects.get(video_id=video_id)
        except VideoTranscript.DoesNotExist:
            logger.warning("Transcript not found for video ID: %s", video_id)
            return Response(
                {"error": "No transcript found for this video."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = VideoTranscriptSerializer(video_transcript)
        return Response(serializer.data)


# ======================
# SECTION VIEWS
# ======================

class VideoSectionListView(generics.ListAPIView):
    """List all sections for a specific video."""
    serializer_class = VideoSectionSerializer

    def get_queryset(self):
        video_id = self.kwargs['video_id']
        return VideoSection.objects.filter(video_id=video_id).order_by('order', 'begin_time')


# ======================
# KNOWLEDGE VIEWS
# ======================

class KnowledgePointsByVideoView(generics.ListAPIView):
    """
    GET /api/videos/<uuid>/knowledge/
    List all knowledge points for a video (flat list).
    """
    serializer_class = KnowledgePointSerializer

    def get_queryset(self):
        video_id = self.kwargs['video_id']
        return KnowledgePoint.objects.filter(
            video_id=video_id
        ).select_related('section').order_by('section__order', 'created_at')


class KnowledgePointsBySectionView(generics.ListAPIView):
    """
    GET /api/sections/<uuid>/knowledge/
    List all knowledge points for a specific section.
    """
    serializer_class = KnowledgePointSerializer

    def get_queryset(self):
        section_id = self.kwargs['section_id']
        return KnowledgePoint.objects.filter(
            section_id=section_id
        ).select_related('section').order_by('created_at')


class SectionsWithKnowledgeView(generics.ListAPIView):
    """
    GET /api/videos/<uuid>/knowledge/grouped/
    List all sections with their nested knowledge points (grouped view).
    """
    serializer_class = SectionWithKnowledgeSerializer

    def get_queryset(self):
        video_id = self.kwargs['video_id']
        return VideoSection.objects.filter(
            video_id=video_id
        ).prefetch_related('knowledge_points').order_by('order', 'begin_time')


# ======================
# EPISODE VIEWS
# ======================

class EpisodeListView(generics.ListAPIView):
    """List all episodes."""
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer


class EpisodeDetailView(generics.RetrieveAPIView):
    """Retrieve a specific episode by ID."""
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer


class EpisodeCreateView(generics.CreateAPIView):
    """Create a new episode."""
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer


class EpisodeDeleteView(generics.DestroyAPIView):
    """DELETE /episodes/<uuid:pk>/ — Delete an episode."""
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer


class EpisodeUpdateView(generics.UpdateAPIView):
    """Update an episode by its `id` field."""
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer
    lookup_field = 'id'


# ======================
# ASYNC TASK VIEWS
# ======================

class AsyncTaskItemCreateView(generics.CreateAPIView):
    """Create a new async task item."""
    queryset = AsyncTaskItem.objects.all()
    serializer_class = AsyncTaskItemSerializer


class AsyncTaskItemDetailView(generics.RetrieveAPIView):
    """Retrieve details of a specific async task."""
    queryset = AsyncTaskItem.objects.all()
    serializer_class = AsyncTaskItemSerializer


class AsyncTaskItemsByVideoView(generics.ListAPIView):
    """List all async tasks associated with a given video."""
    serializer_class = AsyncTaskItemSerializer

    def get_queryset(self):
        video_id = self.kwargs['pk']
        return AsyncTaskItem.objects.filter(video_id=video_id)
