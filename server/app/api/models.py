from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone


class Episode(models.Model):
    """Represents a logical grouping of videos (e.g., a lecture series or show season)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.title

    class Meta:
        ordering = ['-created_at']


class Video(models.Model):
    """Represents an uploaded video file belonging to an episode."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    episode = models.ForeignKey(
        Episode, on_delete=models.SET_NULL, related_name='videos',
        null=True, blank=True, help_text="Optional episode this video belongs to."
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

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='thumbnails')
    time_second = models.FloatField(help_text="Timestamp in seconds where thumbnail was captured.")
    image = models.ImageField(upload_to='thumbnails/')

    def __str__(self) -> str:
        return f"{self.video.title} @ {self.time_second}s"

    class Meta:
        ordering = ['time_second']
        indexes = [models.Index(fields=['video', 'time_second'])]


class VideoTranscript(models.Model):
    """Stores ASR metadata and results for a video. One-to-one with Video."""

    video = models.OneToOneField(
        Video, on_delete=models.CASCADE, primary_key=True,
        help_text="The video this transcript belongs to."
    )
    file_url = models.URLField(help_text="URL to the processed audio file.")
    format = models.CharField(max_length=50, help_text="Audio encoding format.")
    sample_rate = models.IntegerField(help_text="Audio sample rate in Hz.")

    def __str__(self) -> str:
        return f"Transcript for Video {self.video_id}"

    class Meta:
        verbose_name = "Video Transcript"
        verbose_name_plural = "Video Transcripts"


class TranscriptSentence(models.Model):
    """Represents a single transcribed sentence from a video's ASR output."""

    video_transcript = models.ForeignKey(
        VideoTranscript, on_delete=models.CASCADE, related_name='sentences'
    )
    channel_id = models.IntegerField(help_text="Audio channel ID.")
    sentence_id = models.IntegerField(help_text="Unique ID of the sentence within the transcript.")
    begin_time = models.IntegerField(help_text="Start time in milliseconds.")
    end_time = models.IntegerField(help_text="End time in milliseconds.")
    language = models.CharField(max_length=10, help_text="Language code.")
    emotion = models.CharField(max_length=20, blank=True, help_text="Detected speaker emotion.")
    text = models.TextField(help_text="Transcribed sentence text.")

    def __str__(self) -> str:
        return f"Sentence {self.sentence_id} for Video {self.video_transcript.video_id}"

    class Meta:
        ordering = ['begin_time']
        indexes = [models.Index(fields=['video_transcript', 'begin_time'])]


class VideoSection(models.Model):
    """Intelligent segment/chapter produced by the hybrid chunker."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(
        Video, on_delete=models.CASCADE, related_name='sections',
        help_text="Video this section belongs to."
    )
    title = models.CharField(max_length=512, blank=True, help_text="AI-generated section title.")
    begin_time = models.FloatField(help_text="Start time in seconds.")
    end_time = models.FloatField(help_text="End time in seconds.")
    transcript_text = models.TextField(blank=True, help_text="Concatenated transcript text.")
    thumbnail = models.ForeignKey(
        Thumbnail, null=True, blank=True, on_delete=models.SET_NULL,
        help_text="Representative slide thumbnail."
    )
    order = models.IntegerField(default=0, help_text="Section ordering index.")

    def __str__(self) -> str:
        return f"{self.video.title} | Section {self.order}: {self.title or 'Untitled'}"

    class Meta:
        ordering = ['order', 'begin_time']
        indexes = [
            models.Index(fields=['video', 'begin_time']),
            models.Index(fields=['video', 'order']),
        ]


class KnowledgePoint(models.Model):
    """Fine-grained knowledge extracted from a single video section by LLM."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(
        VideoSection, on_delete=models.CASCADE, related_name='knowledge_points',
        help_text="The section this knowledge point was extracted from."
    )
    video = models.ForeignKey(
        Video, on_delete=models.CASCADE, related_name='knowledge_points',
        help_text="Denormalized FK for query efficiency."
    )
    title = models.CharField(max_length=512, help_text="Concise title of the knowledge point.")
    summary = models.TextField(help_text="Detailed explanation (2-3 sentences).")
    key_terms = models.JSONField(default=list, blank=True, help_text="List of key technical terms.")
    importance = models.FloatField(default=0.5, help_text="Importance score 0.0-1.0.")
    embedding_id = models.CharField(max_length=255, blank=True, help_text="Vector DB entry reference.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"KP: {self.title} (Section {self.section.order})"

    class Meta:
        ordering = ['section__order', 'created_at']
        indexes = [
            models.Index(fields=['video', 'section']),
            models.Index(fields=['video', 'created_at']),
        ]


class KnowledgeSummary(models.Model):
    """
    Coarse-grained summary of an entire video, produced by aggregating
    all section knowledge points through LLM.
    One-to-one with Video.
    """

    video = models.OneToOneField(
        Video, on_delete=models.CASCADE, primary_key=True,
        related_name='knowledge_summary',
        help_text="The video this summary belongs to."
    )
    overview = models.TextField(
        help_text="High-level overview paragraph (3-5 sentences)."
    )
    key_topics = models.JSONField(
        default=list, blank=True,
        help_text='Major topics covered, e.g. ["Neural Networks", "Backpropagation"].'
    )
    learning_objectives = models.JSONField(
        default=list, blank=True,
        help_text='What the viewer should learn, e.g. ["Understand gradient descent"].'
    )
    prerequisites = models.JSONField(
        default=list, blank=True,
        help_text='Assumed prerequisite knowledge, e.g. ["Linear algebra basics"].'
    )
    difficulty_level = models.CharField(
        max_length=32, blank=True,
        help_text="Estimated difficulty: beginner/intermediate/advanced."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Summary for Video {self.video_id}"

    class Meta:
        verbose_name = "Knowledge Summary"
        verbose_name_plural = "Knowledge Summaries"


class KnowledgeMindmap(models.Model):
    """
    Hierarchical mindmap structure for a video, produced by LLM
    from sections and knowledge points.
    Stored as a JSON tree that React Flow can render.
    One-to-one with Video.
    """

    video = models.OneToOneField(
        Video, on_delete=models.CASCADE, primary_key=True,
        related_name='knowledge_mindmap',
        help_text="The video this mindmap belongs to."
    )
    tree_data = models.JSONField(
        default=dict,
        help_text=(
            'Hierarchical mindmap tree. Expected structure: '
            '{"id": "root", "label": "...", "children": ['
            '{"id": "...", "label": "...", "children": [...]}]}'
        )
    )
    react_flow_nodes = models.JSONField(
        default=list, blank=True,
        help_text="Pre-computed React Flow nodes array for frontend."
    )
    react_flow_edges = models.JSONField(
        default=list, blank=True,
        help_text="Pre-computed React Flow edges array for frontend."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Mindmap for Video {self.video_id}"

    class Meta:
        verbose_name = "Knowledge Mindmap"
        verbose_name_plural = "Knowledge Mindmaps"


class AsyncTaskItem(models.Model):
    """Unit of async work in a processing pipeline with dependency chaining."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(
        'Video', on_delete=models.CASCADE, related_name='async_tasks',
        help_text="Video this task is associated with."
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    func_name = models.CharField(max_length=64, help_text="Name of the task function to execute.")
    param = models.TextField(help_text="JSON-encoded parameters for the task.")
    result = models.TextField(blank=True, help_text="JSON-encoded result or error message.")
    previous = models.UUIDField(
        null=True, blank=True, editable=True,
        help_text="UUID of the preceding task that must complete first."
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending')
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
