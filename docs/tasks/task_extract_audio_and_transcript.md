# Task: task_extract_audio_and_transcript

## Overview

Extracts the audio track from an uploaded video file, uploads it to Tencent Cloud Object Storage (COS), and submits it to Alibaba DashScope's Qwen3-ASR model for automatic speech recognition. The resulting sentence-level transcript (with timestamps, language detection, and emotion tags) is saved to the database.

**Position in DAG:** Task 1 (parallel, no dependencies)

## Input

```json
{
  "video_id": "uuid-string",
  "file": "videos/lecture1.mp4"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `video_id` | string (UUID) | The video's primary key |
| `file` | string | Relative path to the video file under `MEDIA_ROOT` |

## Output

```json
{
  "video_id": "uuid-string",
  "file": "videos/lecture1.mp4",
  "cos_audio_url": "https://polyu-video-xxx.cos.ap-singapore.myqcloud.com/audio/uuid.wav?sign=..."
}
```

## Processing Steps

### Step 1: Audio Stream Validation

Uses `ffprobe` to check if the video file contains an audio stream:

```
ffprobe -v quiet -select_streams a -show_entries stream=codec_type -of csv=p=0 <video_file>
```

If no audio stream is found, the task fails with a clear error message:
> "Video file has no audio stream. ASR requires an audio track."

### Step 2: Audio Extraction

Uses `ffmpeg` to extract the audio as a 16kHz mono WAV file:

```
ffmpeg -y -i <video_file> -vn -acodec pcm_s16le -ar 16000 -ac 1 <wav_file>
```

- **Output format:** 16-bit PCM WAV
- **Sample rate:** 16,000 Hz (required by Qwen3-ASR)
- **Channels:** Mono
- **Output path:** `media/audio/<video_id>.wav`

### Step 3: COS Upload

Uploads the WAV file to Tencent COS and generates a pre-signed URL (1-hour expiry):

- **Bucket:** Configured via `COS_BUCKET` env var
- **Key:** `audio/<video_id>.wav`
- **Region:** Configured via `COS_REGION` env var

**Required environment variables:**
- `COS_REGION` (e.g., `ap-singapore`)
- `COS_SECRECT_ID` (Tencent Cloud SecretId)
- `COS_SECRECT_KEY` (Tencent Cloud SecretKey)
- `COS_BUCKET` (e.g., `polyu-video-1305580506`)

### Step 4: ASR Transcription

Submits the COS URL to DashScope's Qwen3-ASR file transcription API:

- **Model:** `qwen3-asr-flash-filetrans`
- **Language:** `en` (configurable)
- **API endpoint:** `https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription`
- **Mode:** Asynchronous (submit, poll, fetch result)
- **Timeout:** 600 seconds

**Required environment variable:**
- `DASHSCOPE_API_KEY`

### Step 5: Transcript Persistence

The ASR response is parsed and saved to the database:

- **VideoTranscript** record: file_url, audio format, sample rate
- **TranscriptSentence** records (one per sentence):
  - `sentence_id`, `begin_time` (ms), `end_time` (ms)
  - `text` (transcribed text)
  - `language` (detected language code, e.g., "en", "zh")
  - `emotion` (detected speaker emotion)
  - `channel_id` (audio channel)

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `VideoTranscript` | Create or Update (1:1 with Video) |
| `TranscriptSentence` | Delete existing + bulk create |

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `FileNotFoundError` | Video file doesn't exist on disk | Re-upload the video |
| `RuntimeError: no audio stream` | Video has no audio track | Upload a video with audio |
| `RuntimeError: FFmpeg failed` | Audio extraction error | Check ffmpeg installation |
| `RuntimeError: COS credentials` | Missing env vars | Set COS_* env vars in `.env` |
| `RuntimeError: Transcription failed` | DashScope API error | Check API key, file accessibility |
| `TimeoutError` | ASR took >600s | Increase timeout or use shorter video |

## External Dependencies

- **FFmpeg** / **FFprobe** (system-level, must be on PATH)
- **Tencent COS SDK** (`qcloud_cos`) for cloud storage
- **DashScope API** (`requests`-based client) for ASR

## Approximate Duration

| Video Length | Audio Extraction | COS Upload | ASR Processing | Total |
|-------------|-----------------|------------|----------------|-------|
| 10 min | ~5s | ~10s | ~30-60s | ~1-2 min |
| 60 min | ~15s | ~30s | ~2-5 min | ~3-6 min |
| 120 min | ~30s | ~60s | ~5-10 min | ~6-12 min |
