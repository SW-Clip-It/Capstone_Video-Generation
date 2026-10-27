"""Append-only JSONL logs for generation and upload status."""

import json
import threading
from pathlib import Path
from typing import Any

_WRITE_LOCK = threading.Lock()


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def make_done_key(book_slug: str, text_block_id: str) -> str:
    return f"{book_slug}/{text_block_id}"


def load_done_keys(path: Path) -> set[str]:
    done: set[str] = set()
    if not path.is_file():
        return done
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
                if item.get("book_slug") and item.get("text_block_id"):
                    done.add(make_done_key(item["book_slug"], item["text_block_id"]))
                elif item.get("text_block_id"):
                    done.add(item["text_block_id"])  # Legacy generated-job logs
            except (ValueError, AttributeError, TypeError):
                continue
    return done
