"""CLIP-IT generation entry point: python run.py --help"""

import argparse
import os
from pathlib import Path

from clipit_video.pipeline import run_pipeline

ROOT = Path(__file__).resolve().parent
COMFY_ROOT = Path(os.getenv("COMFYUI_ROOT", "./ComfyUI_LTX2"))
LOG_ROOT = Path(os.getenv("CLIPIT_LOG_DIR", "./logs"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CLIP-IT LTX-2 scene video generation pipeline")
    parser.add_argument("--comfy-url", default=os.getenv("COMFYUI_URL", "http://127.0.0.1:8188"))
    parser.add_argument("--workflow", type=Path, default=ROOT / "workflows/ltx2_t2v_api.json")
    parser.add_argument("--i2v-workflow", type=Path, default=ROOT / "workflows/ltx2_i2v_api.json")
    parser.add_argument("--comfy-input-dir", type=Path, default=COMFY_ROOT / "input")
    parser.add_argument("--input-jsonl", type=Path, default=ROOT / "examples/video_scripts_compact.jsonl")
    parser.add_argument("--output-dir", type=Path, default=COMFY_ROOT / "output")
    parser.add_argument("--book-title", default=None)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--duration", type=int, default=2)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--generated-log", type=Path, default=LOG_ROOT / "generated_jobs.jsonl")
    parser.add_argument("--failed-log", type=Path, default=LOG_ROOT / "failed_jobs.jsonl")
    parser.add_argument("--upload-log", type=Path, default=LOG_ROOT / "uploaded_jobs.jsonl")
    parser.add_argument("--upload-failed-log", type=Path, default=LOG_ROOT / "upload_failed_jobs.jsonl")
    parser.add_argument("--upload-s3", action="store_true")
    parser.add_argument("--upload-workers", type=int, default=2)
    parser.add_argument("--s3-bucket", default=os.getenv("CLIPIT_S3_BUCKET", ""))
    parser.add_argument("--s3-root-prefix", default=os.getenv("CLIPIT_S3_PREFIX", "videos"))
    parser.add_argument("--aws-profile", default=os.getenv("AWS_PROFILE"))
    parser.add_argument("--delete-after-upload", action="store_true")
    parser.add_argument("--max-local-video-count", type=int, default=50)
    parser.add_argument("--poll-sec", type=float, default=2.0)
    parser.add_argument("--timeout-sec", type=int, default=7200)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-nodes", action="store_true")
    parser.add_argument("--strict-chain", action="store_true",
                        help="Fail instead of switching to T2V when a preceding scene is missing")
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0 or args.duration <= 0 or args.fps <= 0:
        parser.error("width, height, duration, and fps must be positive")
    if args.start_index < 0 or (args.limit is not None and args.limit < 0):
        parser.error("start-index and limit must not be negative")
    if args.upload_workers < 1 or args.poll_sec <= 0 or args.timeout_sec <= 0:
        parser.error("upload-workers, poll-sec, and timeout-sec must be positive")
    if args.delete_after_upload and not args.upload_s3:
        parser.error("--delete-after-upload requires --upload-s3")
    return args


if __name__ == "__main__":
    run_pipeline(parse_args())
