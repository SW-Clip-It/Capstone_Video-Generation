"""Asynchronous AWS CLI uploader. Video generation itself remains sequential."""

import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .logs import append_jsonl


def upload_to_s3(video_path: Path, book_slug: str, scene_id: str, *, bucket: str,
                 root_prefix: str, aws_profile: str | None) -> str:
    if not bucket:
        raise ValueError("S3 bucket is required when --upload-s3 is enabled")
    if video_path.suffix.lower() != ".mp4":
        raise ValueError(f"Only MP4 is supported for S3 upload: {video_path}")
    s3_key = "/".join(filter(None, [root_prefix.strip("/"), book_slug, f"{scene_id}.mp4"]))
    s3_uri = f"s3://{bucket}/{s3_key}"
    cmd = ["aws", "s3", "cp", str(video_path), s3_uri, "--content-type", "video/mp4"]
    if aws_profile:
        cmd.extend(["--profile", aws_profile])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError("AWS CLI not found. Install aws and configure credentials.") from exc
    if result.returncode != 0:
        raise RuntimeError(f"S3 upload failed: {result.stderr or result.stdout}")
    return s3_uri


class UploadManager:
    """One queue shared by N upload threads. Logs failures without interrupting generation."""

    def __init__(self, *, enabled: bool, workers: int, bucket: str, root_prefix: str,
                 aws_profile: str | None, uploaded_log: Path, failed_log: Path):
        self.enabled = enabled
        self.workers = max(1, workers)
        self.bucket = bucket
        self.root_prefix = root_prefix
        self.aws_profile = aws_profile
        self.uploaded_log = uploaded_log
        self.failed_log = failed_log
        self.queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.threads: list[threading.Thread] = []
        self.uploaded_paths: set[Path] = set()
        self.failed_count = 0
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.enabled:
            return
        if not self.bucket:
            raise ValueError("Set --s3-bucket or CLIPIT_S3_BUCKET before --upload-s3")
        for index in range(self.workers):
            thread = threading.Thread(target=self._worker, args=(index,), daemon=True)
            thread.start()
            self.threads.append(thread)
        print(f"[UPLOAD WORKERS STARTED] {len(self.threads)}")

    def enqueue(self, video_path: Path, book_slug: str, scene_id: str) -> None:
        if self.enabled:
            self.queue.put({"video_path": str(video_path), "book_slug": book_slug,
                            "text_block_id": scene_id})
            print(f"[UPLOAD QUEUED] {book_slug}/{scene_id}.mp4")

    def _worker(self, worker_id: int) -> None:
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                path = Path(item["video_path"])
                uri = upload_to_s3(path, item["book_slug"], item["text_block_id"],
                                   bucket=self.bucket, root_prefix=self.root_prefix,
                                   aws_profile=self.aws_profile)
                append_jsonl(self.uploaded_log, {**item, "s3_uri": uri, "worker_id": worker_id,
                                                  "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S")})
                with self._lock:
                    self.uploaded_paths.add(path)
                print(f"[S3 SAVED] {uri}")
            except Exception as exc:
                print(f"[S3 UPLOAD FAILED] {item}: {exc}")
                append_jsonl(self.failed_log, {"item": item, "error": str(exc), "worker_id": worker_id,
                                                     "failed_at": time.strftime("%Y-%m-%d %H:%M:%S")})
                with self._lock:
                    self.failed_count += 1
            finally:
                self.queue.task_done()

    def finish(self) -> None:
        if not self.threads:
            return
        self.queue.join()
        for _ in self.threads:
            self.queue.put(None)
        self.queue.join()
        for thread in self.threads:
            thread.join()
        print(f"[UPLOAD FINISHED] success={len(self.uploaded_paths)}, failed={self.failed_count}")
