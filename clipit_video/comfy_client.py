"""Minimal synchronous ComfyUI HTTP API client."""

import time
import uuid
from typing import Any

import requests


class ComfyUIClient:
    def __init__(self, url: str, poll_sec: float = 2.0, timeout_sec: int = 7200):
        self.url = url.rstrip("/")
        self.poll_sec = poll_sec
        self.timeout_sec = timeout_sec

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        response = requests.post(f"{self.url}/prompt", json={"prompt": workflow,
                                 "client_id": str(uuid.uuid4())}, timeout=120)
        response.raise_for_status()
        result = response.json()
        if not result.get("prompt_id"):
            raise RuntimeError(f"ComfyUI did not return a prompt ID: {result}")
        return str(result["prompt_id"])

    def wait_for_history(self, prompt_id: str) -> dict[str, Any]:
        start = time.monotonic()
        while time.monotonic() - start < self.timeout_sec:
            response = requests.get(f"{self.url}/history/{prompt_id}", timeout=120)
            response.raise_for_status()
            item = response.json().get(prompt_id)
            if item is not None:
                status = item.get("status", {})
                status_str = status.get("status_str")
                if status_str and status_str != "success":
                    raise RuntimeError(f"ComfyUI generation failed: {status}")
                return item
            time.sleep(self.poll_sec)
        raise TimeoutError(f"ComfyUI generation timed out: prompt_id={prompt_id}")
