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
    Video, Thumbnail, VideoTranscript, VideoSection, KnowledgePoint,
    KnowledgeSummary, KnowledgeMindmap, Episode, AsyncTaskItem,
)
from .serializers import (
    VideoSerializer, ThumbnailSerializer, VideoUploadSerializer,
    VideoTranscriptSerializer, VideoSectionSerializer,
    KnowledgePointSerializer, SectionWithKnowledgeSerializer,
    KnowledgeSummarySerializer, KnowledgeMindmapSerializer,
    EpisodeSerializer, AsyncTaskItemSerializer, TriggerTaskSerializer,
)

logger = logging.getLogger('polyu-video')


# ======================
# HEALTH CHECK
# ======================

@api_view(['GET'])
def health_check(request):
    db_ok = True
    try:
        connection.ensure_connection()
    except Exception:
        db_ok = False
    storage_ok = os.path.isdir(settings.MEDIA_ROOT)
    all_ok = db_ok and storage_ok
    return Response({
        "ok": all_ok, "ready": all_ok,
        "db": "connected" if db_ok else "error",
        "storage": settings.MEDIA_ROOT if storage_ok else "error",
    }, status=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE)


# ======================
# VIDEO VIEWS
# ======================

class VideoListView(generics.ListAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer

class VideoDetailView(generics.RetrieveAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer

class VideoDeleteView(generics.DestroyAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer

class VideoUpdateView(generics.UpdateAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer
    lookup_field = 'id'

class ThumbnailListView(generics.ListAPIView):
    serializer_class = ThumbnailSerializer
    def get_queryset(self):
        return Thumbnail.objects.filter(video_id=self.kwargs['video_id']).order_by('time_second')
    def get_serializer_context(self) -> Dict[str, Any]:
        return {'request': self.request}

class VideoUploadView(generics.CreateAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoUploadSerializer
    parser_classes = [MultiPartParser, FormParser]
    def post(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            os.makedirs(os.path.join(settings.MEDIA_ROOT, "videos"), exist_ok=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VideoTaskTriggerView(generics.GenericAPIView):
    """POST /api/videos/process/ — Trigger the full processing pipeline."""
    serializer_class = TriggerTaskSerializer

    def post(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        video_id = serializer.validated_data['id']
        video = get_object_or_404(Video, id=video_id)
        if video.async_tasks.filter(status__in=['pending', 'running']).exists():
            return Response(
                {"error": "Tasks already exist for this video (pending or running)."},
                status=status.HTTP_409_CONFLICT
            )
        try:
            self._create_processing_chain(video)
        except Exception as e:
            logger.exception("Failed to create task chain for video %s: %s", video.id, e)
            return Response(
                {"error": "Task initialization failed", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _create_processing_chain(self, video: Video) -> None:
        """
        Task DAG (10 tasks):
          T1 (ASR), T2 (HLS), T3 (SSIM) — parallel
          T4 (Thumbnails) <- T3
          T5 (Hybrid Chunking) <- T4
          T6 (Fine-Grained Knowledge) <- T5
          T7 (Embed Knowledge) <- T6
          T8 (Coarse Summary) <- T7
          T9 (Mindmap) <- T8
          T10 (Final Summary) <- T9
        """
        t1 = AsyncTaskItem.objects.create(
            video=video, title="Extract audio & generate transcript",
            description="Extract audio, upload to COS, transcribe with Qwen-ASR",
            func_name="task_extract_audio_and_transcript",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None)
        t2 = AsyncTaskItem.objects.create(
            video=video, title="Generate HLS",
            description="Generate HLS multi-resolution streaming",
            func_name="task_hls_streaming",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None)
        t3 = AsyncTaskItem.objects.create(
            video=video, title="SSIM Motion Detection",
            description="Detect significant frame changes with SSIM",
            func_name="task_ssim_move_detection",
            param=json.dumps({"video_id": str(video.id), "file": video.file.name}),
            previous=None)
        t4 = AsyncTaskItem.objects.create(
            video=video, title="Generate thumbnails",
            description="Create preview thumbnails at slide changes",
            func_name="task_generate_thumbnails",
            param=json.dumps({"video_id": str(video.id)}),
            previous=t3.id)
        t5 = AsyncTaskItem.objects.create(
            video=video, title="Hybrid video chunking",
            description="Combine SSIM + ASR for intelligent segmentation",
            func_name="task_hybrid_chunking",
            param=json.dumps({"video_id": str(video.id)}),
            previous=t4.id)
        t6 = AsyncTaskItem.objects.create(
            video=video, title="Extract knowledge points",
            description="LLM extraction of structured knowledge from sections",
            func_name="task_fine_grained_knowledge",
            param=json.dumps({"video_id": str(video.id)}),
            previous=t5.id)
        t7 = AsyncTaskItem.objects.create(
            video=video, title="Embed knowledge vectors",
            description="Generate embeddings and store in vector DB",
            func_name="task_embed_knowledge",
            param=json.dumps({"video_id": str(video.id)}),
            previous=t6.id)
        t8 = AsyncTaskItem.objects.create(
            video=video, title="Generate coarse summary",
            description="LLM aggregation of knowledge into video-level summary",
            func_name="task_coarse_grained_summary",
            param=json.dumps({"video_id": str(video.id)}),
            previous=t7.id)
        t9 = AsyncTaskItem.objects.create(
            video=video, title="Generate knowledge mindmap",
            description="LLM generation of hierarchical mindmap with React Flow layout",
            func_name="task_generate_mindmap",
            param=json.dumps({"video_id": str(video.id)}),
            previous=t8.id)


# ======================
# TRANSCRIPT VIEWS
# ======================

class TranscriptDetailView(generics.GenericAPIView):
    def get(self, request, video_id: str, format=None) -> Response:
        try:
            vt = VideoTranscript.objects.get(video_id=video_id)
        except VideoTranscript.DoesNotExist:
            return Response({"error": "No transcript found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(VideoTranscriptSerializer(vt).data)


# ======================
# SECTION VIEWS
# ======================

class VideoSectionListView(generics.ListAPIView):
    serializer_class = VideoSectionSerializer
    def get_queryset(self):
        return VideoSection.objects.filter(video_id=self.kwargs['video_id']).order_by('order')


# ======================
# KNOWLEDGE VIEWS
# ======================

class KnowledgePointsByVideoView(generics.ListAPIView):
    serializer_class = KnowledgePointSerializer
    def get_queryset(self):
        return KnowledgePoint.objects.filter(
            video_id=self.kwargs['video_id']
        ).select_related('section').order_by('section__order', 'created_at')

class KnowledgePointsBySectionView(generics.ListAPIView):
    serializer_class = KnowledgePointSerializer
    def get_queryset(self):
        return KnowledgePoint.objects.filter(
            section_id=self.kwargs['section_id']
        ).select_related('section').order_by('created_at')

class SectionsWithKnowledgeView(generics.ListAPIView):
    serializer_class = SectionWithKnowledgeSerializer
    def get_queryset(self):
        return VideoSection.objects.filter(
            video_id=self.kwargs['video_id']
        ).prefetch_related('knowledge_points').order_by('order')


# ======================
# SUMMARY + MINDMAP VIEWS
# ======================

class KnowledgeSummaryDetailView(generics.GenericAPIView):
    """GET /api/videos/<uuid>/summary/ — Retrieve the coarse-grained summary."""
    def get(self, request, video_id: str, format=None) -> Response:
        try:
            summary = KnowledgeSummary.objects.get(video_id=video_id)
        except KnowledgeSummary.DoesNotExist:
            return Response(
                {"error": "No summary available. Process the video first."},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(KnowledgeSummarySerializer(summary).data)


class KnowledgeMindmapDetailView(generics.GenericAPIView):
    """GET /api/videos/<uuid>/mindmap/ — Retrieve the knowledge mindmap with React Flow data."""
    def get(self, request, video_id: str, format=None) -> Response:
        try:
            mindmap = KnowledgeMindmap.objects.get(video_id=video_id)
        except KnowledgeMindmap.DoesNotExist:
            return Response(
                {"error": "No mindmap available. Process the video first."},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(KnowledgeMindmapSerializer(mindmap).data)


# ======================
# EPISODE VIEWS
# ======================

class EpisodeListView(generics.ListAPIView):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer

class EpisodeDetailView(generics.RetrieveAPIView):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer

class EpisodeCreateView(generics.CreateAPIView):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer

class EpisodeDeleteView(generics.DestroyAPIView):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer

class EpisodeUpdateView(generics.UpdateAPIView):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer
    lookup_field = 'id'


# ======================
# ASYNC TASK VIEWS
# ======================

class AsyncTaskItemCreateView(generics.CreateAPIView):
    queryset = AsyncTaskItem.objects.all()
    serializer_class = AsyncTaskItemSerializer

class AsyncTaskItemDetailView(generics.RetrieveAPIView):
    queryset = AsyncTaskItem.objects.all()
    serializer_class = AsyncTaskItemSerializer

class AsyncTaskItemsByVideoView(generics.ListAPIView):
    serializer_class = AsyncTaskItemSerializer
    def get_queryset(self):
        return AsyncTaskItem.objects.filter(video_id=self.kwargs['pk'])
