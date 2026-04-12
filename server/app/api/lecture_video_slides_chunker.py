"""
Module for detecting slide change timestamps in educational videos.

This module analyzes consecutive video frames to detect significant visual
changes, which often correspond to PowerPoint or PDF slide transitions.
It uses Structural Similarity Index (SSIM) as the primary metric for change
detection and outputs a list of timestamps (in seconds) where slides likely
changed.

Dependencies:
    - opencv-python (cv2)
    - scikit-image (for SSIM)
    - numpy
"""

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim
from typing import List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import threading

def _resize_frame(frame: np.ndarray, target_width: int = 640) -> np.ndarray:
    """
    Resize a video frame to a target width while preserving aspect ratio.

    Reducing resolution speeds up SSIM computation and reduces noise from
    minor pixel-level variations.

    Args:
        frame (np.ndarray): Input frame in BGR format (H x W x 3).
        target_width (int): Desired width in pixels. Height is scaled proportionally.
            Defaults to 640.

    Returns:
        np.ndarray: Resized frame in BGR format.
    """
    height, width = frame.shape[:2]
    scale = target_width / width
    new_height = int(height * scale)
    resized = cv2.resize(frame, (target_width, new_height), interpolation=cv2.INTER_AREA)
    return resized


def _convert_to_grayscale(frame: np.ndarray) -> np.ndarray:
    """
    Convert a BGR frame to grayscale.

    SSIM is typically computed on single-channel images for efficiency and
    robustness.

    Args:
        frame (np.ndarray): Input frame in BGR format (H x W x 3).

    Returns:
        np.ndarray: Grayscale frame (H x W).
    """
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def detect_slide_changes(
    video_path: str,
    ssim_threshold: float = 0.7,
    min_interval_sec: float = 1.0,
    resize_width: int = 640,
    sampling_fps: Optional[float] = None,
) -> List[float]:
    """
    Detect timestamps (in seconds) where slide changes occur in a video.

    This function processes the video frame-by-frame (or at a reduced sampling
    rate), computes SSIM between consecutive frames, and flags a slide change
    when SSIM drops below `ssim_threshold`. To avoid duplicate detections,
    a minimum time interval between changes is enforced.

    Args:
        video_path (str): Path to the input video file.
        ssim_threshold (float): SSIM value below which a frame difference is
            considered a slide change. Lower values mean more sensitive detection.
            Typical range: [0.5, 0.9]. Defaults to 0.7.
        min_interval_sec (float): Minimum time (in seconds) between two detected
            slide changes to suppress jitter/false positives. Defaults to 1.0.
        resize_width (int): Width (in pixels) to which frames are resized before
            SSIM computation. Smaller values increase speed. Defaults to 640.
        sampling_fps (Optional[float]): If provided, video is sampled at this
            frame rate (e.g., 1.0 for 1 FPS). If None, every frame is processed.
            Useful for long videos. Defaults to None.

    Returns:
        List[float]: Sorted list of slide change timestamps in seconds (e.g., [12.4, 45.2]).

    Raises:
        FileNotFoundError: If the video file does not exist or cannot be opened.
        ValueError: If input parameters are invalid (e.g., negative threshold).
    """
    if not (0.0 < ssim_threshold < 1.0):
        raise ValueError("ssim_threshold must be between 0.0 and 1.0 (exclusive).")
    if min_interval_sec < 0:
        raise ValueError("min_interval_sec must be non-negative.")
    if resize_width <= 0:
        raise ValueError("resize_width must be positive.")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        raise ValueError("Invalid video FPS detected.")

    # Determine step size if sampling is enabled
    frame_step = 1
    if sampling_fps is not None:
        if sampling_fps <= 0:
            raise ValueError("sampling_fps must be positive if provided.")
        frame_step = max(1, int(round(fps / sampling_fps)))

    prev_gray: Optional[np.ndarray] = None
    frame_count: int = 0
    slide_change_timestamps: List[float] = []
    last_change_frame: int = -1

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Skip frames according to sampling strategy
        if frame_count % frame_step != 0:
            frame_count += 1
            continue

        # Compute time since last detected slide change
        time_since_last_sec = (
            float('inf') if last_change_frame == -1
            else (frame_count - last_change_frame) / fps
        )

        # Preprocess current frame
        resized = _resize_frame(frame, target_width=resize_width)
        gray = _convert_to_grayscale(resized)

        if prev_gray is not None:
            # Only compute SSIM if we are outside the cooldown window
            if time_since_last_sec >= min_interval_sec:
                # Ensure spatial alignment (robust to rare resizing artifacts)
                min_h = min(prev_gray.shape[0], gray.shape[0])
                min_w = min(prev_gray.shape[1], gray.shape[1])
                prev_crop = prev_gray[:min_h, :min_w]
                curr_crop = gray[:min_h, :min_w]

                ssim_score = ssim(prev_crop, curr_crop)

                if ssim_score < ssim_threshold:
                    current_time_sec = frame_count / fps
                    slide_change_timestamps.append(current_time_sec)
                    last_change_frame = frame_count

        prev_gray = gray.copy()
        frame_count += 1

    cap.release()

    # Remove duplicates and sort (should already be sorted, but ensure)
    slide_change_timestamps = sorted(set(slide_change_timestamps))
    return slide_change_timestamps



def _compute_ssim_pair(
    prev_gray: np.ndarray, curr_gray: np.ndarray, frame_index: int
) -> Tuple[int, float]:
    """
    Compute SSIM between two grayscale frames.

    This function is designed to be executed in a worker thread.

    Args:
        prev_gray (np.ndarray): Previous grayscale frame.
        curr_gray (np.ndarray): Current grayscale frame.
        frame_index (int): Frame index of the current frame (for ordering).

    Returns:
        Tuple[int, float]: (frame_index, ssim_score)
    """
    min_h = min(prev_gray.shape[0], curr_gray.shape[0])
    min_w = min(prev_gray.shape[1], curr_gray.shape[1])
    prev_crop = prev_gray[:min_h, :min_w]
    curr_crop = curr_gray[:min_h, :min_w]
    score = ssim(prev_crop, curr_crop)
    return frame_index, score


def detect_slide_changes_multithreaded(
    video_path: str,
    ssim_threshold: float = 0.7,
    min_interval_sec: float = 1.0,
    resize_width: int = 640,
    sampling_fps: Optional[float] = None,
    num_workers: int = 4,
    progress_callback: Optional[callable] = None,
) -> List[float]:
    """
    Detect slide change timestamps using multithreading for SSIM computation.

    Video decoding remains single-threaded (as required by OpenCV), but SSIM
    calculations are offloaded to a thread pool. This improves performance on
    multi-core systems without compromising frame order or timing.

    Args:
        video_path (str): Path to the input video file.
        ssim_threshold (float): SSIM value below which a frame difference is
            considered a slide change. Defaults to 0.7.
        min_interval_sec (float): Minimum time (in seconds) between accepted
            slide changes. Also used to skip SSIM during cooldown. Defaults to 1.0.
        resize_width (int): Width to resize frames before processing. Defaults to 640.
        sampling_fps (Optional[float]): If set, process video at this frame rate.
            Defaults to None (process every frame).
        num_workers (int): Number of threads for SSIM computation. Defaults to 4.

    Returns:
        List[float]: Sorted list of slide change timestamps in seconds.

    Raises:
        FileNotFoundError: If video cannot be opened.
        ValueError: If parameters are invalid.
    """
    if not (0.0 < ssim_threshold < 1.0):
        raise ValueError("ssim_threshold must be between 0.0 and 1.0 (exclusive).")
    if min_interval_sec < 0:
        raise ValueError("min_interval_sec must be non-negative.")
    if resize_width <= 0:
        raise ValueError("resize_width must be positive.")
    if num_workers < 1:
        raise ValueError("num_workers must be at least 1.")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        raise ValueError("Invalid video FPS detected.")

    frame_step = 1
    if sampling_fps is not None:
        if sampling_fps <= 0:
            raise ValueError("sampling_fps must be positive if provided.")
        frame_step = max(1, int(round(fps / sampling_fps)))

    # Calculate total frames to process for progress tracking
    total_frames_to_process = total_frames // frame_step if total_frames > 0 else 0

    prev_gray: Optional[np.ndarray] = None
    frame_count: int = 0
    processed_count: int = 0
    slide_change_timestamps: List[float] = []
    last_change_frame: int = -1

    # Use ThreadPoolExecutor for SSIM tasks
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Dictionary to map futures to frame indices
        future_to_frame: dict = {}

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_count % frame_step != 0:
                frame_count += 1
                continue

            # Preprocess current frame
            resized = _resize_frame(frame, target_width=resize_width)
            gray = _convert_to_grayscale(resized)

            if prev_gray is not None:
                time_since_last_sec = (
                    float('inf') if last_change_frame == -1
                    else (frame_count - last_change_frame) / fps
                )

                # Only submit SSIM task if outside cooldown window
                if time_since_last_sec >= min_interval_sec:
                    # Submit SSIM computation to thread pool
                    future = executor.submit(_compute_ssim_pair, prev_gray, gray, frame_count)
                    future_to_frame[future] = frame_count

            prev_gray = gray.copy()
            frame_count += 1
            processed_count += 1

            # Report progress every ~5% or every 50 frames
            if progress_callback and total_frames_to_process > 0:
                if processed_count % 50 == 0 or processed_count == 1:
                    progress_pct = min(95, int((processed_count / total_frames_to_process) * 100))
                    progress_callback(progress_pct)

            # Process completed SSIM tasks to avoid memory buildup
            # We process them as they complete to maintain responsiveness
            done_futures = [f for f in future_to_frame if f.done()]
            for future in done_futures:
                try:
                    comp_frame_index, ssim_score = future.result()
                except Exception as exc:
                    # In production, you might log this
                    continue
                finally:
                    future_to_frame.pop(future, None)

                # Only accept if still valid (cooldown may have been updated by newer detections)
                time_since_last_now = (
                    float('inf') if last_change_frame == -1
                    else (comp_frame_index - last_change_frame) / fps
                )
                if time_since_last_now >= min_interval_sec and ssim_score < ssim_threshold:
                    timestamp_sec = comp_frame_index / fps
                    slide_change_timestamps.append(timestamp_sec)
                    last_change_frame = comp_frame_index

        # Process any remaining futures after video ends
        for future in as_completed(future_to_frame):
            comp_frame_index = future_to_frame[future]
            try:
                _, ssim_score = future.result()
            except Exception:
                continue

            time_since_last_now = (
                float('inf') if last_change_frame == -1
                else (comp_frame_index - last_change_frame) / fps
            )
            if time_since_last_now >= min_interval_sec and ssim_score < ssim_threshold:
                timestamp_sec = comp_frame_index / fps
                slide_change_timestamps.append(timestamp_sec)
                last_change_frame = comp_frame_index

    cap.release()
    if progress_callback:
        progress_callback(100)

    # Remove duplicates and sort
    return sorted(set(slide_change_timestamps))


# Example usage (uncomment for testing)
#if __name__ == "__main__":
    # changes = detect_slide_changes(
    #     video_path="/home/xuranus/Downloads/zoom.mp4",
    #     ssim_threshold=0.65,
    #     min_interval_sec=1.5,
    #     resize_width=480,
    #     sampling_fps=2.0
    # )
    # changes = detect_slide_changes_multithreaded(
    #     video_path="/home/xuranus/Downloads/zoom.mp4",
    #     ssim_threshold=0.7,
    #     min_interval_sec=5.0,
    #     resize_width=240,
    #     sampling_fps=10.0,
    #     num_workers=16,
    # ) 
    # print("Detected slide changes (seconds):", changes)