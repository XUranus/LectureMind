from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone


class Episode(models.Model):
    """Represents a logical grouping of videos (e.g., a lecture series or show season)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['-created_at']


class Video(models.Model):
    """Represents an uploaded video file belonging to an episode."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    episode = models.ForeignKey(
        Episode,
        on_delete=models.SET_NULL,
        related_name='videos',
        null=True,
        blank=True,
        help_text="Optional episode this video belongs to."
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='videos/')
    duration = models.FloatField(help_text="Duration in seconds", default=0.0)
    cover = models.CharField(max_length=1024, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['-created_at']


class Thumbnail(models.Model):
    """Represents a preview image extracted from a video at a specific time."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='thumbnails')
    time_second = models.FloatField(help_text="Timestamp in seconds where thumbnail was captured.")
    image = models.ImageField(upload_to='thumbnails/')

    def __str__(self) -> str:
        return f"{self.video.title} @ {self.time_second}s"

    class Meta:
        ordering = ['time_second']
        indexes = [
            models.Index(fields=['video', 'time_second']),
        ]


class VideoTranscript(models.Model):
    """
    Stores automatic speech recognition (ASR) metadata and results for a video.

    Each transcript is associated with exactly one video.
    """

    video = models.OneToOneField(
        Video,
        on_delete=models.CASCADE,
        primary_key=True,  # Enforces 1:1 and uses Video's UUID as PK
        help_text="The video this transcript belongs to."
    )
    file_url = models.URLField(help_text="URL to the processed audio file.")
    format = models.CharField(max_length=50, help_text="Audio encoding format (e.g., 'pcm_s16le').")
    sample_rate = models.IntegerField(help_text="Audio sample rate in Hz (e.g., 16000).")

    def __str__(self) -> str:
        return f"Transcript for Video {self.video_id}"

    class Meta:
        verbose_name = "Video Transcript"
        verbose_name_plural = "Video Transcripts"


class TranscriptSentence(models.Model):
    """
    Represents a single transcribed sentence from a video's ASR output.
    """

    video_transcript = models.ForeignKey(
        VideoTranscript,
        on_delete=models.CASCADE,
        related_name='sentences'
    )
    channel_id = models.IntegerField(help_text="Audio channel ID (for multi-channel audio).")
    sentence_id = models.IntegerField(help_text="Unique ID of the sentence within the transcript.")
    begin_time = models.IntegerField(help_text="Start time in milliseconds.")
    end_time = models.IntegerField(help_text="End time in milliseconds.")
    language = models.CharField(max_length=10, help_text="Language code (e.g., 'en', 'zh').")
    emotion = models.CharField(max_length=20, blank=True, help_text="Detected speaker emotion (optional).")
    text = models.TextField(help_text="Transcribed sentence text.")

    def __str__(self) -> str:
        return f"Sentence {self.sentence_id} for Video {self.video_transcript.video_id}"

    class Meta:
        ordering = ['begin_time']
        indexes = [
            models.Index(fields=['video_transcript', 'begin_time']),
        ]


class AsyncTaskItem(models.Model):
    """
    Represents a unit of asynchronous work in a processing pipeline.

    Tasks may depend on the completion of a previous task via the `previous` UUID reference.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(
        'Video',
        on_delete=models.CASCADE,
        related_name='async_tasks',
        help_text="Video this task is associated with."
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    func_name = models.CharField(max_length=64, help_text="Name of the Celery/task function to execute.")
    param = models.TextField(help_text="JSON-encoded parameters for the task.")
    result = models.TextField(blank=True, help_text="JSON-encoded result or error message.")

    previous = models.UUIDField(
        null=True,
        blank=True,
        editable=True,
        help_text="UUID of the preceding task that must complete before this one starts."
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['previous']),
            models.Index(fields=['video', 'status']),
        ]