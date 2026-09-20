"""VLM region-detection prototype (the roadmap's Phase 2 baseline experiment).

Coordinate handling — the part that usually silently breaks:
  Qwen2.5-VL outputs boxes in ABSOLUTE pixels of the image it sees. We
  pre-resize every page so dims are exact multiples of 28 (patch 14 x
  merge 2) and pass min_pixels=max_pixels=area, which makes the
  processor's smart_resize a no-op. Therefore the model's coordinate
  space == the image we sent, and the scale factor back to the original
  is exact. Boxes are stored NORMALIZED (0..1) — resolution-independent.

If visualizations ever show all boxes piled in one corner, the model
drifted into a different coordinate space — that is a bug to report,
not noise.
"""
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PIL import Image

from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("detection")

MERGE_FACTOR = 28


def pin_size(img: Image.Image) -> Image.Image:
    """Resize to long-edge target with dims as multiples of 28 (see header)."""
    target = config.pipeline.rendering.vlm_long_edge_px
    r = target / max(img.size)
    w = max(MERGE_FACTOR, round(img.width * r / MERGE_FACTOR) * MERGE_FACTOR)
    h = max(MERGE_FACTOR, round(img.height * r / MERGE_FACTOR) * MERGE_FACTOR)
    return img.resize((w, h), Image.LANCZOS)


@dataclass
class Detection:
    region_class: str
    box_norm: List[float]   # [x1, y1, x2, y2] in 0..1
    content_hint: str = ""


class VlmRegionDetector:
    def __init__(self, model_id: Optional[str] = None):
        try:
            import torch
            from transformers import (AutoProcessor,
                                      Qwen2_5_VLForConditionalGeneration)
        except ImportError as e:
            raise RuntimeError(
                "VLM dependencies missing. Run: uv sync --extra vlm") from e
        self.torch = torch
        self.model_id = model_id or config.models["extraction"]["default_vlm"]
        log.info("loading %s (bf16, single GPU)...", self.model_id)
        self.processor = AutoProcessor.from_pretrained(self.model_id)
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_id, torch_dtype=torch.bfloat16, device_map="cuda:0")
        self.classes = (config.regions.extraction_classes
                        + config.regions.discard_classes)
        self.prompt = self._build_prompt()

    def _build_prompt(self) -> str:
        return (
            "You are looking at a scanned page from a periodic medical "
            "examination report. Detect every region of these classes:\n"
            + "\n".join(f"- {c}" for c in self.classes) + "\n\n"
            "Rules:\n"
            "1. photo, thumbprint, signature, stamp_seal are DISCARD classes "
            "(box them so they can be excluded later).\n"
            "2. Typed text and handwritten text are separate regions. A "
            "printed table containing handwritten values is ONE region of "
            "class data_table_handwritten (box the whole table).\n"
            "3. Boxes must not overlap. Only box what is actually visible.\n"
            "4. Coordinates are absolute pixels of THIS image, "
            "[x1, y1, x2, y2], top-left origin.\n\n"
            "Output ONLY a JSON array, nothing else:\n"
            '[{"class": "<class>", "box": [x1, y1, x2, y2], '
            '"content_hint": "<few words>"}]'
        )

    def ask(self, img: Image.Image, prompt: str) -> str:
        """Low-level: send one pinned image + any prompt, return raw text."""
        messages = [{"role": "user", "content": [
            {"type": "image"}, {"type": "text", "text": prompt}]}]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = self.processor(
            text=[text], images=[img],
            min_pixels=img.width * img.height,
            max_pixels=img.width * img.height,
            return_tensors="pt",
        ).to(self.model.device)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=1500,
                                      do_sample=False)
        return self.processor.batch_decode(
            out[:, inputs.input_ids.shape[1]:], skip_special_tokens=True)[0]

    @staticmethod
    def _parse_boxes(text: str) -> List[dict]:
        text = re.sub(r"```(json)?", "", text).strip()
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return []
        try:
            return [d for d in json.loads(m.group(0)) if isinstance(d, dict)]
        except json.JSONDecodeError:
            return []

    def detect(self, image_path: Path) -> List[Detection]:
        with Image.open(image_path) as im:
            orig = im.convert("RGB")
        sent = pin_size(orig)
        t0 = time.time()
        raw = self.ask(sent, self.prompt)
        dt = time.time() - t0

        dets, clamped = [], 0
        for d in self._parse_boxes(raw):
            box = d.get("box")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                continue
            try:
                x1, y1, x2, y2 = (float(v) for v in box)
            except (TypeError, ValueError):
                continue
            for v in (x1, y1, x2, y2):           # coordinate-space sanity probe
                if v > max(sent.size):
                    clamped += 1
            x1, x2 = sorted((x1, x2)); y1, y2 = sorted((y1, y2))
            nx1 = min(max(x1 / sent.width, 0.0), 1.0)
            nx2 = min(max(x2 / sent.width, 0.0), 1.0)
            ny1 = min(max(y1 / sent.height, 0.0), 1.0)
            ny2 = min(max(y2 / sent.height, 0.0), 1.0)
            if (nx2 - nx1) < 0.002 or (ny2 - ny1) < 0.002:
                continue                            # degenerate box
            cls = str(d.get("class", "")).strip().lower()
            dets.append(Detection(
                region_class=cls if cls in self.classes else "unknown",
                box_norm=[nx1, ny1, nx2, ny2],
                content_hint=str(d.get("content_hint", ""))[:80]))
        if clamped > 4:
            log.warning("%s: %d out-of-range coordinates — possible "
                        "coordinate-space drift, check the visualization!",
                        image_path.name, clamped)
        log.info("%s: %d regions in %.1fs", image_path.name, len(dets), dt)
        return dets