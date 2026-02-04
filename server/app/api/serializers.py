# api/serializers.py
from rest_framework import serializers
from .models import Episode, Video, Thumbnail, VideoTranscript, TranscriptSentence, AsyncTaskItem

class ThumbnailSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Thumbnail
        fields = ['id', 'time_second', 'image_url']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class VideoSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    #thumbnails = ThumbnailSerializer(many=True, read_only=True)
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = ['id', 'title', 'video_url', 'duration']

    def get_video_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class VideoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ['title', 'file']  # Only accept these on upload
    
    def to_representation(self, instance):
        # Use the full serializer for output
        return VideoSerializer(instance, context=self.context).data
    

class TranscriptSentenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSentence
        fields = ['channel_id', 'sentence_id', 'begin_time', 'end_time', 'language', 'emotion', 'text']

class VideoTranscriptSerializer(serializers.ModelSerializer):
    sentences = TranscriptSentenceSerializer(many=True, read_only=True)

    class Meta:
        model = VideoTranscript
        fields = ['video_id', 'file_url', 'format', 'sample_rate', 'sentences']


class EpisodeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    videos = VideoSerializer(many=True, read_only=True)

    class Meta:
        model = Episode
        fields = ['id', 'title', 'description', 'created_at', 'videos']


class AsyncTaskItemSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AsyncTaskItem
        fields = ['id', 'video', 'title', 'description', 'created_at', 'finished_at', 'payload', 'status']
        read_only_fields = ['id', 'created_at', 'finished_at']  # id is auto-generated; timestamps managed by model
