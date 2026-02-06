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
        """
        Return the absolute URL of the thumbnail image if available.

        Args:
            obj (Thumbnail): The thumbnail instance.

        Returns:
            Optional[str]: Absolute image URL or None if no image.
        """
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
        """
        Return the absolute URL to the video file.

        Args:
            obj (Video): The video instance.

        Returns:
            Optional[str]: Absolute video URL or None if no file.
        """
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
    On output, returns full video representation via VideoSerializer.
    """

    class Meta:
        model = Video
        fields = ['title', 'file', 'episode']

    def to_representation(self, instance: Video) -> Dict[str, Any]:
        """Use VideoSerializer for output representation."""
        return VideoSerializer(instance, context=self.context).data


class TriggerTaskSerializer(serializers.Serializer):
    """
    Serializer to validate a request to trigger async processing for a video.
    
    Expects a valid UUID of an existing video.
    """
    id = serializers.UUIDField()

    def validate_id(self, value: str) -> str:
        """
        Validate that a Video with the given ID exists.

        Note: Field name is 'id', so validator must be `validate_id`, not `validate_video_id`.

        Args:
            value (str): UUID string of the video.

        Returns:
            str: Validated video ID.

        Raises:
            serializers.ValidationError: If video does not exist.
        """
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