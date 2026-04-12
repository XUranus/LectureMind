# api/serializers.py
from typing import Any, Dict, Optional
from rest_framework import serializers
from .models import (
    Episode, Video, Thumbnail, VideoTranscript, TranscriptSentence,
    VideoSection, KnowledgePoint, KnowledgeSummary, KnowledgeMindmap, SlideOCR,
    ChatSession, ChatMessage, AsyncTaskItem, SystemConfig,
)


class ThumbnailSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    image_url = serializers.SerializerMethodField()
    class Meta:
        model = Thumbnail
        fields = ['id', 'time_second', 'image_url']
    def get_image_url(self, obj):
        if not obj.image: return None
        req = self.context.get('request')
        return req.build_absolute_uri(obj.image.url) if req else obj.image.url



class SlideOCRSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    class Meta:
        model = SlideOCR
        fields = ['id', 'thumbnail', 'video', 'ocr_text', 'time_second', 'thumbnail_url', 'created_at']
        read_only_fields = ['id', 'created_at']
    def get_thumbnail_url(self, obj):
        if not obj.thumbnail or not obj.thumbnail.image: return None
        req = self.context.get('request')
        return req.build_absolute_uri(obj.thumbnail.image.url) if req else obj.thumbnail.image.url


class VideoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    video_url = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    class Meta:
        model = Video
        fields = ['id', 'cover', 'cover_url', 'title', 'video_url', 'duration']
        read_only_fields = ['id', 'cover', 'cover_url', 'video_url', 'duration']
    def get_video_url(self, obj):
        if not obj.file: return None
        req = self.context.get('request')
        return req.build_absolute_uri(obj.file.url) if req else obj.file.url
    def get_cover_url(self, obj):
        if not obj.cover: return None
        req = self.context.get('request')
        return req.build_absolute_uri(obj.cover) if req else obj.cover


class VideoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ['title', 'file', 'episode']
    def to_representation(self, instance):
        return VideoSerializer(instance, context=self.context).data


class TriggerTaskSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    def validate_id(self, value):
        if not Video.objects.filter(id=value).exists():
            raise serializers.ValidationError("Video with this ID does not exist.")
        return value


class TranscriptSentenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSentence
        fields = ['channel_id', 'sentence_id', 'begin_time', 'end_time', 'language', 'emotion', 'text']


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
        fields = ['id', 'video', 'title', 'begin_time', 'end_time', 'transcript_text', 'thumbnail_url', 'order']
        read_only_fields = ['id']
    def get_thumbnail_url(self, obj):
        if not obj.thumbnail or not obj.thumbnail.image: return None
        req = self.context.get('request')
        return req.build_absolute_uri(obj.thumbnail.image.url) if req else obj.thumbnail.image.url


class KnowledgePointSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    section_title = serializers.CharField(source='section.title', read_only=True)
    section_order = serializers.IntegerField(source='section.order', read_only=True)
    begin_time = serializers.FloatField(source='section.begin_time', read_only=True)
    end_time = serializers.FloatField(source='section.end_time', read_only=True)
    class Meta:
        model = KnowledgePoint
        fields = ['id', 'section', 'video', 'title', 'summary', 'key_terms', 'importance', 'created_at',
                  'section_title', 'section_order', 'begin_time', 'end_time']
        read_only_fields = ['id', 'created_at']


class SectionWithKnowledgeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    knowledge_points = KnowledgePointSerializer(many=True, read_only=True)
    class Meta:
        model = VideoSection
        fields = ['id', 'video', 'title', 'begin_time', 'end_time', 'transcript_text', 'thumbnail_url', 'order', 'knowledge_points']
        read_only_fields = ['id']
    def get_thumbnail_url(self, obj):
        if not obj.thumbnail or not obj.thumbnail.image: return None
        req = self.context.get('request')
        return req.build_absolute_uri(obj.thumbnail.image.url) if req else obj.thumbnail.image.url


class KnowledgeSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeSummary
        fields = ['video', 'overview', 'key_topics', 'learning_objectives', 'prerequisites', 'difficulty_level', 'created_at', 'updated_at']
        read_only_fields = ['video', 'created_at', 'updated_at']


class KnowledgeMindmapSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeMindmap
        fields = ['video', 'tree_data', 'react_flow_nodes', 'react_flow_edges', 'created_at', 'updated_at']
        read_only_fields = ['video', 'created_at', 'updated_at']


class ChatMessageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    class Meta:
        model = ChatMessage
        fields = ['id', 'session', 'role', 'content', 'citations', 'created_at']
        read_only_fields = ['id', 'created_at']


class ChatSessionSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    message_count = serializers.SerializerMethodField()
    class Meta:
        model = ChatSession
        fields = ['id', 'video', 'title', 'created_at', 'updated_at', 'message_count']
        read_only_fields = ['id', 'created_at', 'updated_at']
    def get_message_count(self, obj):
        return obj.messages.count()


class ChatSessionDetailSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    messages = ChatMessageSerializer(many=True, read_only=True)
    class Meta:
        model = ChatSession
        fields = ['id', 'video', 'title', 'created_at', 'updated_at', 'messages']
        read_only_fields = ['id', 'created_at', 'updated_at']


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
        fields = ['id', 'video', 'title', 'description', 'func_name', 'result', 'previous', 'created_at', 'finished_at', 'status', 'progress']
        read_only_fields = ['id', 'created_at', 'finished_at']


class SystemConfigSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=128)
    value = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True, required=False)
