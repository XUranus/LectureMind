from django.shortcuts import render, get_object_or_404
from django.conf import settings
from rest_framework import generics, status
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
    Episode,
    AsyncTaskItem,
)
from .serializers import (
    VideoSerializer,
    ThumbnailSerializer,
    VideoUploadSerializer,
    VideoTranscriptSerializer,
    EpisodeSerializer,
    AsyncTaskItemSerializer,
    TriggerTaskSerializer,
)

logger = logging.getLogger('polyu-video')


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
    POST /api/videos/<video_id>/trigger-tasks/

    Triggers an asynchronous processing pipeline for an existing video.
    Ensures no duplicate active task chains are created.
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

        # Avoid creating duplicate active task chains
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

        Task dependencies:
          - Task 1 (ASR), Task 2 (HLS), Task 3 (SSIM) run in parallel.
          - Task 4 (Thumbnails) depends on Task 3.
          - Task 5 (Summary) depends on Task 4.
        """
        # Task 1: ASR + COS upload
        task1 = AsyncTaskItem.objects.create(
            video=video,
            title="Extract audio & generate transcript",
            description="Extract audio track, upload video to COS, transcribe with Qwen-ASR",
            func_name="task_extract_audio_and_transcript",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None
        )
        logger.debug("Created Task1 (ASR): %s for video %s", task1.id, video.id)

        # Task 2: HLS streaming
        task2 = AsyncTaskItem.objects.create(
            video=video,
            title="Generate HLS",
            description="Generate HLS with multiple resolutions for online streaming",
            func_name="task_hls_streaming",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None
        )
        logger.debug("Created Task2 (HLS): %s for video %s", task2.id, video.id)

        # Task 3: SSIM-based motion detection
        task3 = AsyncTaskItem.objects.create(
            video=video,
            title="SSIM Motion Detection",
            description="Use SSIM algorithm to detect significant frame changes",
            func_name="task_ssim_move_detection",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None
        )
        logger.debug("Created Task3 (SSIM): %s for video %s", task3.id, video.id)

        # Task 4: Thumbnails (depends on SSIM)
        task4 = AsyncTaskItem.objects.create(
            video=video,
            title="Generate video thumbnails",
            description="Create preview thumbnails using processed video data",
            func_name="task_generate_thumbnails",
            param=json.dumps({"video_id": str(video.id)}),
            previous=task3.id
        )
        logger.debug("Created Task4 (Thumbnails): %s | Depends on: %s", task4.id, task3.id)

        # Task 5: AI Summary (depends on Thumbnails)
        task5 = AsyncTaskItem.objects.create(
            video=video,
            title="Generate content summary",
            description="Create AI-generated summary using transcript and metadata",
            func_name="task_generate_summary",
            param=json.dumps({"video_id": str(video.id)}),
            previous=task4.id
        )
        logger.debug("Created Task5 (Summary): %s | Depends on: %s", task5.id, task4.id)


class TranscriptDetailView(generics.GenericAPIView):
    """
    Retrieve the transcript for a specific video by video_id.
    """

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