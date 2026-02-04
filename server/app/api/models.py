from django.db import models
import uuid

class Episode(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Video(models.Model):
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='videos', default=None, null=True)
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='videos/')
    duration = models.FloatField(help_text="Duration in seconds", default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Thumbnail(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='thumbnails')
    time_second = models.FloatField()
    image = models.ImageField(upload_to='thumbnails/')

    class Meta:
        ordering = ['time_second']

    def __str__(self):
        return f"{self.video.title} @ {self.time_second}s"
    

class VideoTranscript(models.Model):
    """
    Model representing a video's ASR transcript.

    Attributes:
        video_id (UUID): Unique identifier for the video.
        file_url (str): URL of the audio file.
        format (str): Audio format (e.g., 'pcm_s16le').
        sample_rate (int): Sample rate in Hz (e.g., 16000).
    """

    video_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file_url = models.URLField()
    format = models.CharField(max_length=50)
    sample_rate = models.IntegerField()

    def __str__(self):
        return f"Video Transcript {self.video_id}"


class TranscriptSentence(models.Model):
    """
    Model representing a single sentence from a video transcript.

    Attributes:
        video_transcript (VideoTranscript): ForeignKey to the parent VideoTranscript.
        channel_id (int): Channel ID of the audio stream.
        sentence_id (int): Identifier for the sentence.
        begin_time (int): Start time of the sentence in milliseconds.
        end_time (int): End time of the sentence in milliseconds.
        language (str): Language of the sentence.
        emotion (str): Emotion detected in the sentence.
        text (str): Text of the sentence.
    """

    video_transcript = models.ForeignKey(VideoTranscript, on_delete=models.CASCADE, related_name='sentences')
    channel_id = models.IntegerField()
    sentence_id = models.IntegerField()
    begin_time = models.IntegerField()
    end_time = models.IntegerField()
    language = models.CharField(max_length=10)
    emotion = models.CharField(max_length=20)
    text = models.TextField()

    def __str__(self):
        return f"Sentence {self.sentence_id} for Video {self.video_transcript.video_id}"

    

class AsyncTaskItem(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='async_task')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(auto_now_add=True)
    payload = models.CharField(max_length=1024)
    status = models.CharField(max_length=32) # 'pending' | 'running' | 'done'

    def __str__(self):
        return self.title