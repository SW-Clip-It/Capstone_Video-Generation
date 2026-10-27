"""End-to-end scene orchestration: T2V -> I2V(last frame) -> S3 upload."""

import argparse
import random
import time
import traceback
from pathlib import Path
from typing import Any

from .comfy_client import ComfyUIClient
from .jobs import read_jsonl_jobs, slugify
from .logs import append_jsonl, load_done_keys, make_done_key
from .storage import UploadManager
from .video_io import (cleanup_old_videos, extract_last_frame, extract_output_paths,
                       fallback_find_latest_video, find_previous_scene_video,
                       last_frame_image_name, rename_to_final_path, wait_until_file_stable)
from .workflows import load_workflow, prepare_workflow, print_workflow_nodes


def _previous_video(args: argparse.Namespace, book_slug: str, job: dict[str, Any],
                    chained_path: Path | None) -> Path | None:
    try:
        chapter, scene_number = int(job["chapter"]), int(job["scene_number"])
    except (ValueError, TypeError, KeyError):
        # For jobs without structured scene indices, retain original input-order chaining.
        return chained_path
    if scene_number <= 1:
        return None  # A chapter's first scene is always T2V.
    expected_id = f"{chapter}_{scene_number - 1}"
    if chained_path is not None and chained_path.stem == expected_id:
        return chained_path
    # Never chain an unrelated scene when a chapter has missing/non-consecutive jobs.
    return find_previous_scene_video(args.output_dir, book_slug, job)


def _should_have_predecessor(job: dict[str, Any]) -> bool:
    try:
        return int(job.get("scene_number")) > 1
    except (TypeError, ValueError):
        return False


def run_one_job(args: argparse.Namespace, client: ComfyUIClient,
                t2v_base: dict[str, Any], i2v_base: dict[str, Any],
                job: dict[str, Any], book_slug: str, previous_video: Path | None,
                upload_manager: UploadManager) -> Path | None:
    scene_id = job["text_block_id"]
    previous_video = _previous_video(args, book_slug, job, previous_video)
    if previous_video is None and _should_have_predecessor(job):
        msg = f"Previous scene missing for {scene_id}: falling back to T2V (visual continuity may break)"
        if args.strict_chain:
            raise FileNotFoundError(msg)
        print(f"[CHAIN WARNING] {msg}")

    mode = "I2V" if previous_video is not None else "T2V"
    seed = args.seed if args.seed is not None else random.randint(1, 2**63 - 1)
    image_name = None
    if mode == "I2V":
        if not args.dry_run:
            if not previous_video.is_file():
                raise FileNotFoundError(f"Previous video not found: {previous_video}")
            _, image_name = extract_last_frame(previous_video, args.comfy_input_dir,
                                               book_slug, previous_video.stem)
        else:
            # The dry run prepares the workflow but never calls FFmpeg.
            image_name = last_frame_image_name(book_slug, previous_video.stem)

    workflow = prepare_workflow(t2v_base if mode == "T2V" else i2v_base, job, book_slug,
                                width=args.width, height=args.height, duration=args.duration,
                                fps=args.fps, seed=seed, mode=mode, image_name=image_name)
    print(f"[GENERATION] book={book_slug}, scene={scene_id}, mode={mode}, seed={seed}")
    if args.dry_run:
        print(f"[DRY RUN] workflow validated for {scene_id}; ComfyUI/FFmpeg/S3 not called")
        return None

    start_ts = time.time()
    prompt_id = client.queue_prompt(workflow)
    print(f"[COMFY QUEUED] {prompt_id}")
    history_item = client.wait_for_history(prompt_id)
    candidates = [p for p in extract_output_paths(history_item, args.output_dir) if p.is_file()]
    generated = candidates[0] if candidates else fallback_find_latest_video(
        args.output_dir, book_slug, scene_id, start_ts)
    if generated is None:
        raise RuntimeError(f"No generated video found for {scene_id} (prompt_id={prompt_id})")
    wait_until_file_stable(generated)
    final_path = rename_to_final_path(generated, args.output_dir, book_slug, scene_id)
    print(f"[VIDEO SAVED] {final_path} ({final_path.stat().st_size / 1024**2:.2f} MB)")

    if args.upload_s3:
        upload_manager.enqueue(final_path, book_slug, scene_id)
    append_jsonl(args.generated_log, {
        "book_slug": book_slug, "text_block_id": scene_id, "generation_mode": mode,
        "input_image": image_name, "prompt_id": prompt_id,
        "local_video_path": str(final_path),
        "target_upload_name": f"videos/{book_slug}/{scene_id}.mp4",
        "s3_uri": None, "upload_status": "queued" if args.upload_s3 else "skipped",
        "chapter": job.get("chapter"), "scene_number": job.get("scene_number"),
        "width": args.width, "height": args.height, "duration": args.duration,
        "fps": args.fps, "seed": seed, "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    return final_path


def run_pipeline(args: argparse.Namespace) -> None:
    if args.upload_s3 and args.dry_run:
        print("[DRY RUN] no S3 upload worker will be started")
    book_slug = slugify(args.book_title) if args.book_title else slugify(args.input_jsonl.stem)
    t2v_base = load_workflow(args.workflow)
    i2v_base = load_workflow(args.i2v_workflow)
    if args.print_nodes:
        print("===== T2V WORKFLOW NODES =====")
        print_workflow_nodes(t2v_base)
        print("===== I2V WORKFLOW NODES =====")
        print_workflow_nodes(i2v_base)
        return

    jobs = read_jsonl_jobs(args.input_jsonl)
    if args.start_index:
        jobs = jobs[args.start_index:]
    if args.limit is not None:
        jobs = jobs[:args.limit]
    done_keys = load_done_keys(args.generated_log)
    print(f"[PIPELINE START] book={book_slug}, jobs={len(jobs)}, already_generated={len(done_keys)}")
    client = ComfyUIClient(args.comfy_url, args.poll_sec, args.timeout_sec)
    uploader = UploadManager(enabled=args.upload_s3 and not args.dry_run,
                             workers=args.upload_workers, bucket=args.s3_bucket,
                             root_prefix=args.s3_root_prefix, aws_profile=args.aws_profile,
                             uploaded_log=args.upload_log, failed_log=args.upload_failed_log)
    uploader.start()
    previous_video: Path | None = None
    previous_chapter: Any = None
    generated_count = 0
    failed_count = 0
    try:
        for index, job in enumerate(jobs):
            scene_id, chapter = job["text_block_id"], job.get("chapter")
            if index > 0 and chapter != previous_chapter:
                print(f"[CHAPTER CHANGE] {previous_chapter} -> {chapter}; reset scene chain")
                previous_video = None
            previous_chapter = chapter
            key = make_done_key(book_slug, scene_id)
            if key in done_keys and not args.dry_run:
                existing = args.output_dir / "videos" / book_slug / f"{scene_id}.mp4"
                previous_video = existing if existing.is_file() else None
                print(f"[SKIP GENERATED] {key}; local chaining video: {previous_video}")
                continue
            try:
                path = run_one_job(args, client, t2v_base, i2v_base, job, book_slug,
                                   previous_video, uploader)
                generated_count += 1
                if args.dry_run:
                    # Synthetic next-scene path for validating sequential T2V/I2V choices.
                    previous_video = args.output_dir / "videos" / book_slug / f"{scene_id}.mp4"
                else:
                    previous_video = path
                    done_keys.add(key)
            except Exception as exc:
                failed_count += 1
                print(f"[JOB FAILED] book={book_slug}, scene={scene_id}: {exc}")
                traceback.print_exc()
                if not args.dry_run:
                    append_jsonl(args.failed_log, {"book_slug": book_slug, "text_block_id": scene_id,
                                                   "chapter": chapter, "scene_number": job.get("scene_number"),
                                                   "error": str(exc),
                                                   "failed_at": time.strftime("%Y-%m-%d %H:%M:%S")})
                previous_video = None
    finally:
        uploader.finish()
        if not args.dry_run:
            # Avoid the original race: do not delete a video while it is needed for
            # chaining or still queued for upload. Deletion happens after all jobs.
            if args.delete_after_upload:
                for path in sorted(uploader.uploaded_paths):
                    if path.is_file():
                        path.unlink()
                        print(f"[LOCAL DELETED AFTER UPLOAD] {path}")
            if args.upload_s3 and uploader.failed_count:
                print("[CLEANUP SKIPPED] S3 upload failures detected; retain local videos for retry")
            else:
                cleanup_old_videos(args.output_dir, args.max_local_video_count)
    print(f"[PIPELINE FINISHED] generated={generated_count}, failed={failed_count}, "
          f"upload_failures={uploader.failed_count}")
