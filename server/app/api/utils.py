import os
import uuid
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Union, Tuple, Optional
from PIL import Image
import shutil
from urllib.parse import urlparse
from django.conf import settings

def get_local_file_path(relative_path: str) -> str:
    """
    Convert a media URL to an absolute local filesystem path.
    
    Args:
        relative_path (str): relative path of the media file (e.g., 'videos/file.mp4')
    
    Returns:
        str: Absolute local file path (e.g., '/var/www/myproject/media/videos/file.mp4')
    
    Raises:
        ValueError: If URL doesn't belong to this site's MEDIA_URL
    """
    # Join with MEDIA_ROOT to get absolute path
    local_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    return os.path.abspath(local_path)


def generate_thumbnails_for_video(
    video_file: str,
    time_seconds: List[Union[int, float]],
    width: int,
    output_dir: str
) -> List[Dict[str, Union[str, float]]]:
    """
    Generate thumbnails from a video at specified timestamps, resized to target width.
    
    Args:
        video_file: Path to source video file
        time_seconds: List of timestamps (in seconds) to extract frames
        width: Target width for resized thumbnails (height scaled proportionally)
        output_dir: Directory to save thumbnail images
    
    Returns:
        List of dicts containing:
            - image_id: UUID string used as filename (without extension)
            - time_second: Original timestamp (float)
            - image: Absolute path to saved thumbnail file
    
    Raises:
        FileNotFoundError: If video_file doesn't exist or FFmpeg/Pillow not installed
        ValueError: If width <= 0 or time_seconds empty
        RuntimeError: If FFmpeg extraction fails
    """
    # Validate dependencies
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError("FFmpeg not found. Please install FFmpeg (https://ffmpeg.org)")
    
    # Validate inputs
    if not os.path.isfile(video_file):
        raise FileNotFoundError(f"Video file not found: {video_file}")
    
    if not time_seconds:
        raise ValueError("time_seconds cannot be empty")
    
    if width <= 0:
        raise ValueError(f"Width must be positive (got {width})")
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    results = []
    
    for ts in time_seconds:
        # Generate UUID for this thumbnail
        image_id = str(uuid.uuid4())
        temp_path = os.path.join(output_dir, f"{image_id}_temp.jpg")
        final_path = os.path.join(output_dir, f"{image_id}.jpg")
        
        try:
            # Extract frame at precise timestamp using FFmpeg
            # -ss before -i enables accurate seeking (frame-accurate)
            cmd = [
                "ffmpeg",
                "-ss", str(ts),          # Seek to timestamp first (accurate)
                "-i", video_file,
                "-vframes", "1",         # Extract single frame
                "-vf", "scale='min(iw,1920)':-2",  # Optional: limit source resolution for speed
                "-q:v", "2",             # High quality JPEG (1-31, lower = better)
                "-y",                    # Overwrite existing files
                temp_path
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30  # Prevent hanging on corrupted videos
            )
            
            if result.returncode != 0:
                # Skip invalid timestamps (e.g., beyond video duration)
                print(f"Warning: Failed to extract frame at {ts}s: {result.stderr[:200]}")
                continue
            
            # Resize while maintaining aspect ratio using Pillow
            with Image.open(temp_path) as img:
                # Calculate proportional height
                ratio = width / img.width
                height = int(img.height * ratio)
                
                # Resize with high-quality Lanczos filter
                resized = img.resize((width, height), Image.Resampling.LANCZOS)
                resized = resized.convert("RGB")  # Ensure JPEG compatibility
                resized.save(final_path, "JPEG", quality=95, optimize=True)
            
            # Clean up temp file
            os.remove(temp_path)
            
            # Add to results
            results.append({
                "image_id": image_id,
                "time_second": float(ts),
                "image": final_path
            })
            
        except Exception as e:
            # Clean up temp files on error
            for p in (temp_path, final_path):
                if os.path.exists(p):
                    os.remove(p)
            print(f"Warning: Error processing timestamp {ts}s: {e}")
            continue
    
    return results


def generate_hls_renditions(
    input_video_path: str,
    video_id: str,
    output_root: str = "/output",
    resolutions: List[Tuple[int, int]] = [(1920, 1080)], #[(1920, 1080), (1280, 720), (854, 480), (640, 360)],
    hls_time: int = 4,
    hls_list_size: int = 0,  # keep all segments in playlist
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    audio_bitrate: str = "128k",
    preset: str = "fast"
) -> None:
    """
    Transcodes a video into multiple HLS renditions at different resolutions.

    Args:
        input_video_path (str): Path to the source video file.
        video_id (str): Unique identifier for the video.
        output_root (str): Root directory for output (default: "/output").
        resolutions (List[Tuple[int, int]]): List of (width, height) target resolutions.
        hls_time (int): segment duration; used in ffmpeg -hls_time.
        hls_list_size (int): Number of entries in m3u8 playlist (0 = unlimited).
        video_codec (str): Video codec to use (e.g., libx264).
        audio_codec (str): Audio codec (e.g., aac).
        audio_bitrate (str): Audio bitrate (e.g., "128k").
        preset (str): FFmpeg encoding preset (e.g., "fast", "medium").

    Output structure:
        /output/{video_id}/{width}x{height}/
            ├── stream.m3u8
            └── segment_00000.ts, segment_00001.ts, ...
    """
    input_path = Path(input_video_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input video not found: {input_video_path}")

    base_output_dir = Path(output_root) / video_id
    base_output_dir.mkdir(parents=True, exist_ok=True)

    for width, height in resolutions:
        # Create resolution-specific output dir
        res_dir = base_output_dir / f"{width}x{height}"
        res_dir.mkdir(parents=True, exist_ok=True)

        output_m3u8 = res_dir / "stream.m3u8"

        # Construct FFmpeg command
        cmd = [
            "ffmpeg",
            "-i", str(input_path),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", video_codec,
            "-preset", preset,
            "-crf", "23",  # visually lossless quality
            "-c:a", audio_codec,
            "-b:a", audio_bitrate,
            "-hls_time", str(hls_time),
            "-hls_segment_filename", str(res_dir / "segment_%05d.ts"),
            "-hls_list_size", str(hls_list_size),
            "-f", "hls",
            str(output_m3u8)
        ]

        print(f"Encoding to {width}x{height}...")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"✅ Completed {width}x{height}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to encode {width}x{height}: {e.stderr}")
            raise

    print(f"🎉 All renditions generated under: {base_output_dir}")


# Bandwidth estimates (in bits per second) for common resolutions
# You can adjust these based on your actual encoding bitrates
RESOLUTION_TO_BANDWIDTH = {
    (1920, 1080): 5_000_000,   # 5 Mbps
    (1280, 720):  2_800_000,   # 2.8 Mbps
    (854, 480):   1_400_000,   # 1.4 Mbps
    (640, 360):     800_000,   # 800 kbps
    (426, 240):     400_000,   # 400 kbps
}

def parse_resolution_from_dirname(dirname: str) -> Optional[Tuple[int, int]]:
    """Parse '1920x1080' into (1920, 1080). Returns None if invalid."""
    try:
        parts = dirname.split('x')
        if len(parts) != 2:
            return None
        w, h = int(parts[0]), int(parts[1])
        if w <= 0 or h <= 0:
            return None
        return (w, h)
    except ValueError:
        return None

def generate_master_playlist(
    video_id: str,
    output_root: str = "/output",
    output_filename: str = "master.m3u8",
    bandwidth_map: dict = RESOLUTION_TO_BANDWIDTH
) -> str:
    """
    Generates a master.m3u8 file that references all resolution renditions.

    Args:
        video_id (str): Video ID (subdirectory under output_root).
        output_root (str): Root output directory.
        output_filename (str): Name of master playlist file.
        bandwidth_map (dict): Mapping from (w, h) to bandwidth in bps.

    Returns:
        str: Absolute path to generated master.m3u8.
    """
    base_dir = Path(output_root) / video_id
    if not base_dir.exists():
        raise FileNotFoundError(f"Video output directory not found: {base_dir}")

    renditions: List[Tuple[int, int, str]] = []  # (width, height, relative_path)

    for item in base_dir.iterdir():
        if item.is_dir():
            res = parse_resolution_from_dirname(item.name)
            if res and (item / "stream.m3u8").exists():
                relative_path = f"{item.name}/stream.m3u8"
                renditions.append((res[0], res[1], relative_path))

    if not renditions:
        raise ValueError(f"No valid resolution directories found in {base_dir}")

    # Sort by resolution (height ascending)
    renditions.sort(key=lambda x: x[1])

    # Build master playlist content
    lines = ["#EXTM3U"]
    for width, height, rel_path in renditions:
        bandwidth = bandwidth_map.get((width, height), 1_000_000)  # fallback 1 Mbps
        lines.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={width}x{height}'
        )
        lines.append(rel_path)

    master_content = "\n".join(lines) + "\n"

    master_path = base_dir / output_filename
    with open(master_path, "w") as f:
        f.write(master_content)

    print(f"✅ Generated master playlist: {master_path}")
    return str(master_path)


#if __name__ == "__main__":
    # Example usage

    # 1. generate thumbnails
    # thumbnails = generate_thumbnails_for_video(
    #     video_file="/home/xuranus/workspace/LectureMind-Agent/server/app/media/videos/zoom.mp4",
    #     time_seconds=[93.12, 95.04, 264.96, 267.36, 306.24, 308.64, 439.68, 442.08, 446.4, 591.84],
    #     width=200,
    #     output_dir="./media/thumbnails"
    # )

    # for thumb in thumbnails:
    #     print(thumb)
        #{'image_id': '4040a248-8f27-43dd-989f-d86d6ae0a37f', 'time_second': 446.4, 'image': '/home/xuranus/workspace/LectureMind-Agent/server/app/media/thumbnails/4040a248-8f27-43dd-989f-d86d6ae0a37f.jpg'}
        #{'image_id': '52d939b0-5fb4-4c20-b7c9-fd076de8fee4', 'time_second': 591.84, 'image': '/home/xuranus/workspace/LectureMind-Agent/server/app/media/thumbnails/52d939b0-5fb4-4c20-b7c9-fd076de8fee4.jpg'}

    # 2. generate HLS renditions
    # generate_hls_renditions(
    #     input_video_path="/home/xuranus/workspace/LectureMind-Agent/server/app/media/videos/zoom.mp4",
    #     video_id="114514",
    #     output_root="./media/streams"
    # )

    # 3. generate HLS master
    # generate_master_playlist(
    #     video_id="114514",
    #     output_root="./media/streams",
    #     output_filename="master-stream.m3u8"
    # )