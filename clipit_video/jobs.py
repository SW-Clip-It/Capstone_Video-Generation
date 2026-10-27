"""Input JSONL parsing and scene metadata."""

import json
import re
from pathlib import Path
from typing import Any


def slugify(value: Any) -> str:
    text = re.sub(r"\.jsonl$", "", str(value).strip(), flags=re.IGNORECASE).lower()
    text = re.sub(r"[^a-z0-9가-힣]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-") or "unknown-book"


def normalize_id(value: Any) -> str:
    text = str(value).strip().replace("/", "_").replace("\\", "_")
    return re.sub(r"[^a-zA-Z0-9_-]", "_", text) or "unknown-scene"


def extract_prompt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("prompt") or "").strip()
    text = str(value).strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and parsed.get("prompt"):
                return str(parsed["prompt"]).strip()
        except json.JSONDecodeError:
            pass
    return text


def read_jsonl_jobs(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Input JSONL not found: {path}")
    jobs = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[SKIP] invalid JSON line={line_no}: {exc}")
                continue
            if not isinstance(item, dict):
                print(f"[SKIP] non-object JSON line={line_no}")
                continue
            scene_id = normalize_id(item.get("text_block_id") or item.get("scene_id") or f"line_{line_no}")
            script = item.get("video_script")
            prompt = extract_prompt(script.get("prompt")) if isinstance(script, dict) else ""
            prompt = prompt or extract_prompt(item.get("prompt")) or extract_prompt(item.get("final_prompt"))
            if not prompt:
                print(f"[SKIP] empty prompt line={line_no}, id={scene_id}")
                continue
            jobs.append({"text_block_id": scene_id, "prompt": prompt, "chapter": item.get("chapter"),
                         "scene_number": item.get("scene_number"), "raw": item})
    return jobs
