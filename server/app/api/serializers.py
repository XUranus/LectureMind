# api/serializers.py
from typing import Any, Dict, Optional
from rest_framework import serializers
from django.core.exceptions import ValidationError

from .models import (
    Episode, Video, Thumbnail, VideoTranscript, TranscriptSentence,
    VideoSection, KnowledgePoint, KnowledgeSummary, KnowledgeMindmap,
    AsyncTaskItem,
)


class ThumbnailSerializer(serializers.ModelSerializer):
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
    class Meta:
        model = Video
        fields = ['title', 'file', 'episode']

    def to_representation(self, instance: Video) -> Dict[str, Any]:
        return VideoSerializer(instance, context=self.context).data


class TriggerTaskSerializer(serializers.Serializer):
    id = serializers.UUIDField()

    def validate_id(self, value: str) -> str:
        if not Video.objects.filter(id=value).exists():
            raise serializers.ValidationError("Video with this ID does not exist.")
        return value


class TranscriptSentenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSentence
        fields = [
            'channel_id', 'sentence_id', 'begin_time', 'end_time',
            'language', 'emotion', 'text'
        ]


class VideoTranscriptSerializer(serializers.ModelSerializer):
    sentences = TranscriptSentenceSerializer(many=True, read_only=True)

    class Meta:
        model = VideoTranscript
        fields = ['video_id', 'file_url', 'format', 'sample_rate', 'sentences']


class VideoSectionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = VideoSection
        fields = [
            'id', 'video', 'title', 'begin_time', 'end_time',
            'transcript_text', 'thumbnail_url', 'order',
        ]
        read_only_fields = ['id']

    def get_thumbnail_url(self, obj: VideoSection) -> Optional[str]:
        if not obj.thumbnail or not obj.thumbnail.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.thumbnail.image.url)
        return obj.thumbnail.image.url


class KnowledgePointSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    section_title = serializers.CharField(source='section.title', read_only=True)
    section_order = serializers.IntegerField(source='section.order', read_only=True)
    begin_time = serializers.FloatField(source='section.begin_time', read_only=True)
    end_time = serializers.FloatField(source='section.end_time', read_only=True)

    class Meta:
        model = KnowledgePoint
        fields = [
            'id', 'section', 'video', 'title', 'summary',
            'key_terms', 'importance', 'created_at',
            'section_title', 'section_order', 'begin_time', 'end_time',
        ]
        read_only_fields = ['id', 'created_at']


class SectionWithKnowledgeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    knowledge_points = KnowledgePointSerializer(many=True, read_only=True)

    class Meta:
        model = VideoSection
        fields = [
            'id', 'video', 'title', 'begin_time', 'end_time',
            'transcript_text', 'thumbnail_url', 'order',
            'knowledge_points',
        ]
        read_only_fields = ['id']

    def get_thumbnail_url(self, obj: VideoSection) -> Optional[str]:
        if not obj.thumbnail or not obj.thumbnail.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.thumbnail.image.url)
        return obj.thumbnail.image.url


class KnowledgeSummarySerializer(serializers.ModelSerializer):
    """Serialize the coarse-grained video summary."""
    class Meta:
        model = KnowledgeSummary
        fields = [
            'video', 'overview', 'key_topics', 'learning_objectives',
            'prerequisites', 'difficulty_level', 'created_at', 'updated_at',
        ]
        read_only_fields = ['video', 'created_at', 'updated_at']


class KnowledgeMindmapSerializer(serializers.ModelSerializer):
    """Serialize the mindmap with pre-computed React Flow data."""
    class Meta:
        model = KnowledgeMindmap
        fields = [
            'video', 'tree_data', 'react_flow_nodes', 'react_flow_edges',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['video', 'created_at', 'updated_at']


class EpisodeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    videos = VideoSerializer(many=True, read_only=True)

    class Meta:
        model = Episode
        fields = ['id', 'title', 'description', 'created_at', 'videos']
        read_only_fields = ['id', 'created_at']


class AsyncTaskItemSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AsyncTaskItem
        fields = [
            'id', 'video', 'title', 'description',
            'created_at', 'finished_at', 'status'
        ]
        read_only_fields = ['id', 'created_at', 'finished_at']
