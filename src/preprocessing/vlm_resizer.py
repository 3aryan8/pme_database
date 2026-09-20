"""Generates the downsampled VLM-input copies (the two-resolution rule)."""
from PIL import Image

from src.utils.config_loader import config


def make_vlm_copy(cleaned_path, out_path) -> int:
    """Long-edge resize, aspect ratio preserved. Returns final pixel width."""
    target = config.pipeline.rendering.vlm_long_edge_px
    with Image.open(cleaned_path) as im:
        im = im.convert("RGB")
        w, h = im.size
        ratio = target / max(w, h)
        out = im.resize((max(1, round(w * ratio)), max(1, round(h * ratio))),
                        Image.LANCZOS)
        out.save(out_path)
        return out.size[0]