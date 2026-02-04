from django.shortcuts import render
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .models import Video, Thumbnail, VideoTranscript, Episode, \
    AsyncTaskItem

from .serializers import VideoSerializer, ThumbnailSerializer, \
    VideoUploadSerializer, VideoTranscriptSerializer, EpisodeSerializer, \
    AsyncTaskItemSerializer

class VideoListView(generics.ListAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer


class VideoDetailView(generics.RetrieveAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoSerializer


class ThumbnailListView(generics.ListAPIView):
    serializer_class = ThumbnailSerializer

    def get_queryset(self):
        video_id = self.kwargs['video_id']
        return Thumbnail.objects.filter(video_id=video_id).order_by('time_second')

    def get_serializer_context(self):
        return {'request': self.request}


class VideoUploadView(generics.CreateAPIView):
    queryset = Video.objects.all()
    serializer_class = VideoUploadSerializer
    parser_classes = [MultiPartParser, FormParser]  # Required for file uploads

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class TranscriptDetailView(generics.ListAPIView):
    """
    Retrieve the transcript for a specific video by video_id.
    """

    def get(self, request, video_id: str, format=None):
        try:
            video_transcript = VideoTranscript.objects.get(video_id=video_id)
        except VideoTranscript.DoesNotExist:
            return Response({"error": "No transcript found for this video."}, status=status.HTTP_404_NOT_FOUND)

        # Serialize the data
        serializer = VideoTranscriptSerializer(video_transcript)
        return Response(serializer.data)



class EpisodeListView(generics.ListAPIView):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer

class EpisodeDetailView(generics.RetrieveAPIView):
    queryset = Episode.objects.all()
    #queryset = Episode.objects.prefetch_related('videos')  # Optional optimization
    serializer_class = EpisodeSerializer

class EpisodeCreateView(generics.CreateAPIView):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer

class EpisodeDeleteView(generics.DestroyAPIView):
    """DELETE /episodes/<uuid:pk>/"""
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer
    
class AsyncTaskItemCreateView(generics.CreateAPIView):
    queryset = AsyncTaskItem.objects.all()
    serializer_class = AsyncTaskItemSerializer

class AsyncTaskItemDetailView(generics.RetrieveAPIView):
    queryset = AsyncTaskItem.objects.all()
    serializer_class = AsyncTaskItemSerializer

class AsyncTaskItemsByVideoView(generics.ListAPIView):
    serializer_class = AsyncTaskItemSerializer

    def get_queryset(self):
        video_id = self.kwargs['pk']
        return AsyncTaskItem.objects.filter(video_id=video_id)