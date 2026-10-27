"""Locate generated videos, normalize filenames, and extract chaining frames."""

import subprocess
import time
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}


def extract_output_paths(history_item: dict[str, Any], output_dir: Path) -> list[Path]:
    """Read filenames from ComfyUI history output, including nested node output formats."""
    found: list[Path] = []

    def visit(obj: Any) -> None:
        if isinstance(obj, dict):
            if obj.get("filename"):
                found.append(output_dir / str(obj.get("subfolder") or "") / str(obj["filename"]))
            for value in obj.values():
                visit(value)
        elif isinstance(obj, list):
            for value in obj:
                visit(value)

    visit(history_item.get("outputs", {}))
    videos = [path for path in found if path.suffix.lower() in VIDEO_EXTENSIONS]
    return videos if videos else found


def fallback_find_latest_video(output_dir: Path, book_slug: str, scene_id: str, since_ts: float) -> Path | None:
    target_dir = output_dir / "videos" / book_slug
    candidates = [p for p in target_dir.glob(f"{scene_id}*.mp4")
                  if p.is_file() and p.stat().st_mtime >= since_ts] if target_dir.is_dir() else []
    if not candidates and output_dir.is_dir():
        candidates = [p for p in output_dir.rglob("*.mp4")
                      if scene_id in p.name and p.stat().st_mtime >= since_ts]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def wait_until_file_stable(path: Path, interval: float = 2.0, stable_checks: int = 2,
                           timeout_sec: int = 600) -> None:
    start = time.monotonic()
    previous_size, equal_count = -1, 0
    while time.monotonic() - start < timeout_sec:
        size = path.stat().st_size if path.is_file() else -1
        if size > 0 and size == previous_size:
            equal_count += 1
            if equal_count >= stable_checks:
                return
        else:
            equal_count = 0
        previous_size = size
        time.sleep(interval)
    raise TimeoutError(f"Generated video never became stable: {path}")


def rename_to_final_path(generated_path: Path, output_dir: Path, book_slug: str, scene_id: str) -> Path:
    final_dir = output_dir / "videos" / book_slug
    final_dir.mkdir(parents=True, exist_ok=True)
    final_path = final_dir / f"{scene_id}.mp4"
    if generated_path.resolve() == final_path.resolve():
        return final_path
    # Keep original behavior: existing output with the same scene ID is replaced.
    if final_path.exists():
        final_path.unlink()
    generated_path.rename(final_path)
    return final_path


def last_frame_image_name(book_slug: str, scene_id: str) -> str:
    return (Path("last_frames") / book_slug / f"{scene_id}.png").as_posix()


def extract_last_frame(video_path: Path, comfy_input_dir: Path, book_slug: str,
                       scene_id: str) -> tuple[Path, str]:
    """Use FFmpeg to grab one frame near the *end* of a completed video.

    This deliberately preserves the source command's -sseof -0.1 behavior.
    It is not guaranteed to be the mathematically exact final decoded frame.
    """
    image_name = last_frame_image_name(book_slug, scene_id)
    output_path = comfy_input_dir / image_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-sseof", "-0.1", "-i", str(video_path),
           "-frames:v", "1", str(output_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg not found. Install ffmpeg and add it to PATH.") from exc
    if result.returncode != 0 or not output_path.is_file():
        raise RuntimeError(f"Last-frame extraction failed: video={video_path}, stderr={result.stderr}")
    print(f"[LAST FRAME SAVED] {output_path}")
    return output_path, image_name


def find_previous_scene_video(output_dir: Path, book_slug: str, job: dict[str, Any]) -> Path | None:
    """Resume from a previous scene saved under the original chapter_scene convention."""
    try:
        chapter, scene = int(job["chapter"]), int(job["scene_number"])
    except (ValueError, TypeError, KeyError):
        return None
    if scene <= 1:
        return None
    path = output_dir / "videos" / book_slug / f"{chapter}_{scene - 1}.mp4"
    return path if path.is_file() else None


def cleanup_old_videos(output_dir: Path, max_count: int, protected_paths: set[Path] | None = None) -> None:
    """Only call after pending uploads and active scene chains are finished."""
    if max_count <= 0 or not output_dir.is_dir():
        return
    protected = {path.resolve() for path in (protected_paths or set())}
    videos = [path for path in output_dir.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
    if len(videos) <= max_count:
        return
    candidates = sorted((path for path in videos if path.resolve() not in protected),
                        key=lambda path: path.stat().st_mtime)
    for path in candidates[:len(videos) - max_count]:
        print(f"[CLEANUP] {path}")
        path.unlink()
