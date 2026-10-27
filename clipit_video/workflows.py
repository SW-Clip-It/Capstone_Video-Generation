"""Prepare T2V/I2V ComfyUI API workflow graphs without changing the originals."""

import copy
import json
from pathlib import Path
from typing import Any

from .config import I2V_NODES, NEGATIVE_PROMPT, T2V_NODES, WorkflowNodes


def load_workflow(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"ComfyUI API workflow not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        workflow = json.load(handle)
    if not isinstance(workflow, dict):
        raise ValueError(f"Expected ComfyUI API workflow JSON object: {path}")
    return workflow


def prepare_workflow(base: dict[str, Any], job: dict[str, Any], book_slug: str, *,
                     width: int, height: int, duration: int, fps: int, seed: int,
                     mode: str, image_name: str | None = None) -> dict[str, Any]:
    """Populate the original workflow's known parameter nodes for one scene."""
    nodes: WorkflowNodes = T2V_NODES if mode == "T2V" else I2V_NODES if mode == "I2V" else None
    if nodes is None:
        raise ValueError(f"Unknown generation mode: {mode}")
    if mode == "I2V" and not image_name:
        raise ValueError("I2V requires the previous scene's last-frame image")
    workflow = copy.deepcopy(base)
    required = [nodes.prompt, nodes.negative, nodes.width, nodes.height, nodes.duration,
                nodes.fps, nodes.switch, nodes.save_video, *nodes.seeds]
    if nodes.image:
        required.append(nodes.image)
    missing = [node_id for node_id in required if node_id not in workflow]
    if missing:
        raise KeyError(f"Missing {mode} workflow node ID(s): {missing}. Recheck clipit_video/config.py")
    # Inputs match the workflow that the user originally exported.
    workflow[nodes.prompt]["inputs"]["value"] = job["prompt"]
    workflow[nodes.negative]["inputs"]["text"] = NEGATIVE_PROMPT
    for node_id, value in ((nodes.width, width), (nodes.height, height),
                           (nodes.duration, duration), (nodes.fps, fps),
                           (nodes.switch, nodes.switch_value)):
        workflow[node_id]["inputs"]["value"] = value
    for node_id in nodes.seeds:
        workflow[node_id]["inputs"]["noise_seed"] = seed
    if nodes.image:
        workflow[nodes.image]["inputs"]["image"] = image_name
    workflow[nodes.save_video]["inputs"]["filename_prefix"] = f"videos/{book_slug}/{job['text_block_id']}"
    return workflow


def print_workflow_nodes(workflow: dict[str, Any]) -> None:
    for node_id, node in workflow.items():
        print(f"{node_id}: {node.get('class_type')} ({node.get('_meta', {}).get('title')}) "
              f"inputs={list(node.get('inputs', {}))}")
