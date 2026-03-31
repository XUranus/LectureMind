# Task: task_generate_thumbnails

## Overview

Extracts video frames at the timestamps identified by SSIM slide detection, resizes them into thumbnail images, saves them to disk, and sets the first thumbnail as the video's cover image.

**Position in DAG:** Task 4 (depends on T3: task_ssim_move_detection)

## Input

Receives the output of `task_ssim_move_detection` (passed via task chain):

```json
{
  "video_id": "uuid-string",
  "file": "videos/lecture1.mp4",
  "changes": [10.22, 34.56, 78.90, ...]
}
```

## Output

```json
{
  "video_id": "uuid-string",
  "file": "videos/lecture1.mp4",
  "changes": [10.22, 34.56, 78.90, ...],
  "thumbnail_count": 15
}
```

## Processing Steps

### Step 1: Frame Extraction

For each timestamp in `changes`, extracts a single frame using FFmpeg:

```
ffmpeg -ss <timestamp> -i <video_file> -vframes 1 -q:v 2 -y <temp_path>
```

- Uses `-ss` before `-i` for accurate seeking
- Quality setting: `-q:v 2` (high quality JPEG)
- Timeout: 30 seconds per frame

### Step 2: Resize

Each extracted frame is resized to `width=200` pixels (height proportional) using Pillow with Lanczos resampling, then saved as JPEG (quality 95).

### Step 3: Database Update

- All existing thumbnails for the video are deleted (including files on disk)
- New `Thumbnail` records are created with UUID primary keys

### Step 4: Set Video Cover

After all thumbnails are created, the first thumbnail (earliest timestamp) is set as the video's `cover` field:

```python
video.cover = first_thumb.image.url
```

This cover URL is used by the video grid on the `/videos` and `/courses` pages.

## Output File Structure

```
media/thumbnails/
  <uuid1>.jpg   (200px wide, slide at 10.22s)
  <uuid2>.jpg   (200px wide, slide at 34.56s)
  ...
```

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `Thumbnail` | Delete all existing + create new records |
| `Video` | Update `cover` field with first thumbnail URL |

## Error Handling

- Individual frame extraction failures are logged and skipped (the task continues)
- If no frames could be extracted (all failed), `thumbnail_count` will be 0 but the task still succeeds

## External Dependencies

- **FFmpeg** (frame extraction)
- **Pillow** (resize + JPEG encoding)
