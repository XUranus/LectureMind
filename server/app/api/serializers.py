# api/serializers.py
from typing import Any, Dict, Optional

from rest_framework import serializers
from django.core.exceptions import ValidationError

from .models import (
    Episode,
    Video,
    Thumbnail,
    VideoTranscript,
    TranscriptSentence,
    VideoSection,
    AsyncTaskItem,
)


class ThumbnailSerializer(serializers.ModelSerializer):
    """Serialize thumbnail metadata with absolute image URL."""
    id = serializers.UUIDField(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Thumbnail
        fields = ['id', 'time_second', 'image_url']

    def get_image_url(self, obj: Thumbnail) -> Optional[str]:
        if not obj.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url


class VideoSerializer(serializers.ModelSerializer):
    """Serialize video metadata with absolute video file URL."""
    id = serializers.UUIDField(read_only=True)
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = ['id', 'cover', 'title', 'video_url', 'duration']
        read_only_fields = ['id', 'cover', 'video_url', 'duration']

    def get_video_url(self, obj: Video) -> Optional[str]:
        if not obj.file:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url


class VideoUploadSerializer(serializers.ModelSerializer):
    """
    Serializer for uploading a new video.
    Accepts only title, file, and episode during creation.
    """

    class Meta:
        model = Video
        fields = ['title', 'file', 'episode']

    def to_representation(self, instance: Video) -> Dict[str, Any]:
        return VideoSerializer(instance, context=self.context).data


class TriggerTaskSerializer(serializers.Serializer):
    """Validate a request to trigger async processing for a video."""
    id = serializers.UUIDField()

    def validate_id(self, value: str) -> str:
        if not Video.objects.filter(id=value).exists():
            raise serializers.ValidationError("Video with this ID does not exist.")
        return value


class TranscriptSentenceSerializer(serializers.ModelSerializer):
    """Serialize individual transcript sentences."""

    class Meta:
        model = TranscriptSentence
        fields = [
            'channel_id',
            'sentence_id',
            'begin_time',
            'end_time',
            'language',
            'emotion',
            'text'
        ]


class VideoTranscriptSerializer(serializers.ModelSerializer):
    """Serialize full video transcript including all sentences."""
    sentences = TranscriptSentenceSerializer(many=True, read_only=True)

    class Meta:
        model = VideoTranscript
        fields = [
            'video_id',
            'file_url',
            'format',
            'sample_rate',
            'sentences'
        ]


class VideoSectionSerializer(serializers.ModelSerializer):
    """Serialize video sections with thumbnail URL."""
    id = serializers.UUIDField(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = VideoSection
        fields = [
            'id',
            'video',
            'title',
            'begin_time',
            'end_time',
            'transcript_text',
            'thumbnail_url',
            'order',
        ]
        read_only_fields = ['id']

    def get_thumbnail_url(self, obj: VideoSection) -> Optional[str]:
        if not obj.thumbnail or not obj.thumbnail.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.thumbnail.image.url)
        return obj.thumbnail.image.url


class EpisodeSerializer(serializers.ModelSerializer):
    """Serialize episode with nested videos."""
    id = serializers.UUIDField(read_only=True)
    videos = VideoSerializer(many=True, read_only=True)

    class Meta:
        model = Episode
        fields = ['id', 'title', 'description', 'created_at', 'videos']
        read_only_fields = ['id', 'created_at']


class AsyncTaskItemSerializer(serializers.ModelSerializer):
    """Serialize async task items with read-only metadata."""
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AsyncTaskItem
        fields = [
            'id',
            'video',
            'title',
            'description',
            'created_at',
            'finished_at',
            'status'
        ]
        read_only_fields = ['id', 'created_at', 'finished_at']
