# Task: task_ssim_move_detection

## Overview

Analyzes the video frame-by-frame using Structural Similarity Index (SSIM) to detect significant visual changes, which correspond to slide transitions in lecture videos. Outputs a list of timestamps (in seconds) where slides changed.

**Position in DAG:** Task 3 (parallel, no dependencies)

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
  "file": "videos/lecture1.mp4",
  "changes": [10.22, 34.56, 78.90, 120.0, ...]
}
```

The `changes` array contains sorted timestamps (in seconds) where slide transitions were detected. This array is passed to downstream tasks (thumbnails, chunking).

## Algorithm

### SSIM (Structural Similarity Index)

SSIM measures the perceived visual similarity between two images. Values range from 0 (completely different) to 1 (identical). A value below the threshold indicates a slide change.

### Processing Pipeline

1. **Frame sampling:** Read frames at `sampling_fps` rate (default: 10 FPS). At 10 FPS for a 60-minute video, this processes ~36,000 frames instead of ~1.8M at native 30 FPS.

2. **Preprocessing:** Each frame is:
   - Resized to `resize_width=240` pixels wide (height proportional) -- reduces computation
   - Converted to grayscale -- SSIM works on single-channel images

3. **SSIM computation (multithreaded):** Consecutive frames are compared using SSIM. The computation is offloaded to a `ThreadPoolExecutor` with `num_workers=16` threads. Video decoding remains single-threaded (OpenCV requirement).

4. **Change detection:** If SSIM between consecutive frames drops below `ssim_threshold=0.7`, a slide change is recorded at that timestamp.

5. **Cooldown:** A minimum interval of `min_interval_sec=5.0` seconds is enforced between detections to suppress rapid false positives (e.g., animations, transitions).

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ssim_threshold` | 0.7 | SSIM below this = slide change. Lower = more sensitive |
| `min_interval_sec` | 5.0 | Minimum seconds between two detections |
| `resize_width` | 240 | Frame width for SSIM computation (pixels) |
| `sampling_fps` | 10.0 | Process frames at this rate |
| `num_workers` | 16 | Threads for SSIM computation |

## Database Models Affected

None -- results are passed through the task chain as JSON output.

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `FileNotFoundError` | Video file missing | Re-upload |
| `ValueError: Invalid FPS` | Corrupted video | Re-encode video |

## External Dependencies

- **OpenCV** (`cv2`) -- video decoding + frame processing
- **scikit-image** (`skimage.metrics.structural_similarity`) -- SSIM computation
- **NumPy** -- array operations

## Memory Usage

At `resize_width=240`, each grayscale frame is ~240x135 pixels = ~32KB. The thread pool holds at most `num_workers` frame pairs simultaneously, so peak memory is approximately `16 * 2 * 32KB = ~1MB` for the SSIM thread pool, plus the video decoder buffer.

## Approximate Duration

| Video Length | Frames @ 10 FPS | Processing Time |
|-------------|-----------------|-----------------|
| 10 min | ~6,000 | ~10-20s |
| 60 min | ~36,000 | ~60-120s |
| 120 min | ~72,000 | ~2-4 min |
