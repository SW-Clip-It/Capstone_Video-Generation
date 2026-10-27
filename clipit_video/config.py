"""Workflow node mappings and generation defaults.

The IDs below come from the original LTX-2 ComfyUI API workflows.
Update these mappings if you export a different workflow.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowNodes:
    prompt: str
    negative: str
    width: str
    height: str
    duration: str
    fps: str
    seeds: tuple[str, ...]
    switch: str
    save_video: str
    image: str | None = None
    switch_value: bool = True


T2V_NODES = WorkflowNodes(
    prompt="324:320", negative="324:315", width="324:314", height="324:301",
    duration="324:303", fps="324:302", seeds=("324:278", "324:279"),
    switch="324:304", save_video="324:327", switch_value=True,
)

I2V_NODES = WorkflowNodes(
    prompt="320:319", negative="320:313", width="320:312", height="320:299",
    duration="320:301", fps="320:300", seeds=("320:276", "320:277"),
    switch="320:302", image="LAST_FRAME", save_video="SAVE_VIDEO", switch_value=False,
)

NEGATIVE_PROMPT = (
    "low quality, blurry, cartoon, anime, illustration, drawing, painting, "
    "storybook, black and white, monochrome, watermark, logo, text, subtitles, "
    "bad anatomy, extra limbs, flickering, style change"
)
