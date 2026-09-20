"""Phase 5 baseline: full-page, schema-driven extraction (GATE 1 experiment).

- ZERO-SHOT: no few-shot examples, no eval-leakage surface. When Phase 7
  adds few-shots, they must never come from holdout docs
  (scripts/check_holdout_leakage.py enforces).
- Transcription fidelity: values exactly as printed; canonicalization is
  the scorer's job.
- Input resolution is an EXPERIMENT: --source vlm (1280px contracted)
  vs --source raw/clean (~2600px). Measure, don't assume.
"""
import json
import re
import time
from pathlib import Path
from typing import Optional

from PIL import Image

from src.models.fields import (count_non_null, null_shape, prompt_skeleton,
                               prune_to_shape)
from src.models.schemas import SchemaConfig
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("extraction")

MERGE_FACTOR = 28                 # Qwen2.5-VL: patch 14 x merge 2
DEFAULT_LONG_EDGE_HIRES = 2688    # ~300 DPI page long edge, 28-multiple


def _pin_size(img: Image.Image, long_edge: int) -> Image.Image:
    r = long_edge / max(img.size)
    w = max(MERGE_FACTOR, round(img.width * r / MERGE_FACTOR) * MERGE_FACTOR)
    h = max(MERGE_FACTOR, round(img.height * r / MERGE_FACTOR) * MERGE_FACTOR)
    return img.resize((w, h), Image.LANCZOS)


def _section_lines(specs, indent: int = 0) -> list:
    """Human-readable field list for the prompt, nested under sections."""
    lines = []
    pad = "  " * indent
    for s in specs:
        hint = f" — {s.extraction_hint}" if s.extraction_hint else ""
        if s.data_type == "object" and s.children:
            lines.append(f"{pad}- {s.field_name} (object){hint}")
            lines.extend(_section_lines(s.children, indent + 1))
        elif s.data_type == "array" and s.item:
            lines.append(f"{pad}- {s.field_name} (array — one row object per "
                         f"printed table row){hint}")
            for c in (s.item.children or []):
                lbl = (f' — printed label "{c.printed_row_label}"'
                       if c.printed_row_label else "")
                ch = f" ({c.extraction_hint})" if c.extraction_hint else ""
                lines.append(f"{pad}  * item.{c.field_name}: "
                             f"{c.source_type or 'typed'}{lbl}{ch}")
        else:
            lbl = (f' — printed label "{s.printed_row_label}"'
                   if s.printed_row_label else "")
            lines.append(f"{pad}- {s.field_name}: {s.source_type} field{lbl}{hint}")
    return lines


def build_extraction_prompt(schema: SchemaConfig,
                            page: Optional[int] = None,
                            n_pages: Optional[int] = None) -> str:
    """Pure function — unit-testable without a model or GPU.
    `page` (1-based, document-relative) restricts the prompt to sections that
    belong to that page; sections without a `page` are always included.
    `n_pages` (with page=None) sets DOCUMENT mode: all sections in one
    prompt, all page images attached in order (single-pass extraction)."""
    doc_mode = page is None and n_pages is not None
    sections = [s for s in schema.fields
                if page is None or s.page is None or s.page == page]
    if doc_mode:
        intro = ("You are reading the candidate's COMPLETE scanned periodic "
                 "medical examination report (Railway Recruitment Board) — "
                 f"{n_pages} page images attached IN ORDER (page 1 first, "
                 f"page {n_pages} last). Each section below is labelled with "
                 "the page it belongs to; transcribe every field from its own "
                 "page. Some fields may be blank on the form.")
        list_header = "FIELD LIST (transcribe each field from ITS page):\n"
        rule2 = ("If a field is blank on the form, or you cannot read it, "
                 "output null. NEVER guess a plausible value. An empty cell "
                 "is null.\n")
    else:
        intro = ("You are reading ONE page of a scanned periodic medical "
                 "examination report (Railway Recruitment Board). "
                 + (f"This is page {page} of the person's document — only "
                    f"fields that can appear on page {page} are listed below."
                    if page is not None
                    else "Some fields will NOT be on this page."))
        list_header = "FIELD LIST (transcribe from THIS page):\n"
        rule2 = ("If a field is not on this page, or you cannot read it, "
                 "output null. NEVER guess a plausible value. An empty cell "
                 "is null.\n")
    field_list = "\n".join(_section_lines(sections))
    skeleton = json.dumps(prompt_skeleton(sections), indent=2)
    rules = (
        "RULES:\n"
        "1. Transcribe values EXACTLY as printed. Do NOT reformat dates or "
        "numbers. Handwriting: transcribe your best literal reading.\n"
        "2. " + rule2
        + "3. Match printed row labels to locate table fields — column "
        "identity matters; do not swap left/right or systolic/diastolic.\n"
        "4. For array fields, output one row object per printed table row, "
        "in printed order, using exactly the item fields shown.\n"
        "5. For boolean answer fields: true means the candidate answered "
        "'Yes', false means 'No', null means unreadable.\n"
        "6. Output ONLY a JSON object with exactly this shape; every leaf "
        "value is a string or null. No other text.\n")
    return (intro + "\n\n" + list_header
            + field_list + "\n\nOUTPUT SHAPE (copy exactly):\n" + skeleton
            + "\n\n" + rules)


def _first_json_object(text: str) -> Optional[str]:
    """First balanced top-level JSON object in `text` (string-aware)."""
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        start = text.find("{", start + 1)
    return None


def parse_extraction_output(raw: str, schema: SchemaConfig) -> tuple:
    """Tolerant JSON parsing + schema-shape filtering. Pure, testable.
    Returns ({section: shaped value}, parse_ok) — shaped per the schema tree."""
    nulls = null_shape(schema.fields)
    candidate = _first_json_object(re.sub(r"```(json)?", " ", raw))
    if candidate is None:
        return nulls, False
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return nulls, False
    return prune_to_shape(obj, schema.fields), True


class VlmSchemaExtractor:
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
        self.schema = config.schema

    def _ask(self, imgs: list, prompt: str,
             max_new_tokens: int = 800) -> str:
        """One model call; `imgs` = 1 image (per-page) or all pages of one
        person-document (single pass), in order. min/max_pixels bracket the
        per-image sizes so the processor resamples NONE of them (all are
        already 28-aligned multiples of the Qwen patch-merge grid)."""
        content: list = [{"type": "image"} for _ in imgs]
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        lo = min(im.width * im.height for im in imgs)
        hi = max(im.width * im.height for im in imgs)
        inputs = self.processor(
            text=[text], images=list(imgs),
            min_pixels=lo, max_pixels=hi,
            return_tensors="pt").to(self.model.device)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=max_new_tokens,
                                      do_sample=False)
        return self.processor.batch_decode(
            out[:, inputs.input_ids.shape[1]:], skip_special_tokens=True)[0]

    def extract_page(self, image_path: Path, long_edge: int,
                     page: Optional[int] = None) -> tuple:
        """Returns (nested shaped fields dict, parse_ok).
        `page` (1-based, doc-relative) selects the page-specific prompt."""
        with Image.open(image_path) as im:
            img = _pin_size(im.convert("RGB"), long_edge)
        t0 = time.time()
        prompt = build_extraction_prompt(self.schema, page)
        # 2048: the v2 per-page JSON (incl. page-4 table rows) exceeds the
        # old 800 budget and would be truncated -> guaranteed parse failure.
        raw = self._ask([img], prompt, max_new_tokens=2048)
        fields, ok = parse_extraction_output(raw, self.schema)
        log.info("%s (page %s): parse_ok=%s, %d non-null, %.1fs",
                 image_path.name, page, ok,
                 count_non_null(fields, self.schema.fields),
                 time.time() - t0)
        return fields, ok

    def extract_document(self, image_paths: list, long_edge: int) -> tuple:
        """Single pass over ALL pages of one person-document, in page order.
        ONE model call, ONE full-schema JSON (no per-page outputs, no
        cross-page merge needed — the model sees every page at once).
        Returns (nested shaped fields dict, parse_ok)."""
        imgs: list = []
        for p in image_paths:            # order preserved: page 0 first
            with Image.open(p) as im:
                imgs.append(_pin_size(im.convert("RGB"), long_edge))
        t0 = time.time()
        prompt = build_extraction_prompt(self.schema, n_pages=len(imgs))
        raw = self._ask(imgs, prompt, max_new_tokens=4096)  # full v2 JSON
        fields, ok = parse_extraction_output(raw, self.schema)
        log.info("document %d pages: parse_ok=%s, %d non-null, %.1fs",
                 len(imgs), ok, count_non_null(fields, self.schema.fields),
                 time.time() - t0)
        return fields, ok