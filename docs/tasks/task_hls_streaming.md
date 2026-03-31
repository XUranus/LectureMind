# Task: task_hls_streaming

## Overview

Transcodes the uploaded video into HLS (HTTP Live Streaming) format with multiple resolution renditions for adaptive bitrate playback. Generates `.ts` segment files and `.m3u8` playlists.

**Position in DAG:** Task 2 (parallel, no dependencies)

## Input

```json
{
  "video_id": "uuid-string",
  "file": "videos/lecture1.mp4"
}
```

## Output

```json
{
  "video_id": "uuid-string",
  "master_m3u8_path": "media/streams/<video_id>/master-stream.m3u8"
}
```

## Processing Steps

### Step 1: Multi-Resolution Transcoding

For each target resolution, runs an FFmpeg command:

```
ffmpeg -i <input> \
  -vf "scale=<W>:<H>:force_original_aspect_ratio=decrease,pad=<W>:<H>:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 128k \
  -hls_time 4 \
  -hls_segment_filename "<output_dir>/segment_%05d.ts" \
  -hls_list_size 0 \
  -f hls <output_dir>/stream.m3u8
```

**Default resolutions:** 1920x1080 (single rendition for dev; expandable to 720p, 480p, 360p)

**Encoding parameters:**
- Video codec: H.264 (libx264), CRF 23 (visually lossless)
- Audio codec: AAC, 128kbps
- Segment duration: 4 seconds
- Preset: fast

### Step 2: Master Playlist Generation

Scans the output directory for resolution subdirectories containing `stream.m3u8`, then generates a master playlist:

```m3u8
#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080
1920x1080/stream.m3u8
```

**Bandwidth estimates** are set per resolution from a lookup table.

## Output File Structure

```
media/streams/<video_id>/
  master-stream.m3u8
  1920x1080/
    stream.m3u8
    segment_00000.ts
    segment_00001.ts
    ...
```

## Frontend Integration

The Mux video player (`@mux/mux-video-react`) loads:
```
http://localhost:8000/media/streams/<video_id>/master-stream.m3u8
```

If HLS is not yet available, the `StreamVideo` component falls back to serving the raw MP4 file directly, or displays a "Video Processing" placeholder.

## Database Models Affected

None -- this task only writes files to the filesystem.

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `FileNotFoundError` | Input video missing | Re-upload |
| `CalledProcessError` | FFmpeg encoding failure | Check codec support, disk space |

## External Dependencies

- **FFmpeg** (system-level)

## Approximate Duration

| Video Length | 1080p Only | 4 Renditions |
|-------------|-----------|--------------|
| 10 min | ~30-60s | ~2-4 min |
| 60 min | ~3-5 min | ~10-15 min |
| 120 min | ~6-10 min | ~20-30 min |
