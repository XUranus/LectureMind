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
        primary_key=True,
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
    """Represents a single transcribed sentence from a video's ASR output."""

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


class VideoSection(models.Model):
    """
    Represents an intelligent segment/chapter of a video produced by the hybrid chunker.
    Combines SSIM slide detection, ASR silence gaps, and semantic similarity.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name='sections',
        help_text="Video this section belongs to."
    )
    title = models.CharField(
        max_length=512,
        blank=True,
        help_text="AI-generated or human-assigned section title."
    )
    begin_time = models.FloatField(help_text="Start time in seconds.")
    end_time = models.FloatField(help_text="End time in seconds.")
    transcript_text = models.TextField(
        blank=True,
        help_text="Concatenated transcript text for this section."
    )
    thumbnail = models.ForeignKey(
        Thumbnail,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Representative slide thumbnail for this section."
    )
    order = models.IntegerField(
        default=0,
        help_text="Section ordering index."
    )

    def __str__(self) -> str:
        return f"{self.video.title} | Section {self.order}: {self.title or 'Untitled'}"

    class Meta:
        ordering = ['order', 'begin_time']
        indexes = [
            models.Index(fields=['video', 'begin_time']),
            models.Index(fields=['video', 'order']),
        ]


class KnowledgePoint(models.Model):
    """
    Fine-grained knowledge extracted from a single video section.

    Each knowledge point is produced by sending the section's transcript
    (and optionally slide image) to a multimodal LLM for structured extraction.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    section = models.ForeignKey(
        VideoSection,
        on_delete=models.CASCADE,
        related_name='knowledge_points',
        help_text="The section this knowledge point was extracted from."
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name='knowledge_points',
        help_text="The video this knowledge point belongs to (denormalized for query efficiency)."
    )
    title = models.CharField(
        max_length=512,
        help_text="Concise title of the knowledge point."
    )
    summary = models.TextField(
        help_text="Detailed explanation of the knowledge point (2-3 sentences)."
    )
    key_terms = models.JSONField(
        default=list,
        blank=True,
        help_text='List of key technical terms, e.g. ["gradient descent", "learning rate"].'
    )
    importance = models.FloatField(
        default=0.5,
        help_text="Importance score from 0.0 (low) to 1.0 (high)."
    )
    embedding_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Reference to vector DB entry for semantic retrieval."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"KP: {self.title} (Section {self.section.order})"

    class Meta:
        ordering = ['section__order', 'created_at']
        indexes = [
            models.Index(fields=['video', 'section']),
            models.Index(fields=['video', 'created_at']),
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
    func_name = models.CharField(max_length=64, help_text="Name of the task function to execute.")
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
