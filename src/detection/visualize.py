"""Draw detection boxes on the page render — the human-review artifact."""
from pathlib import Path

from PIL import Image, ImageDraw

COLORS = {
    "typed_text": (0, 120, 215),
    "handwritten_text": (255, 140, 0),
    "data_table_typed": (0, 160, 120),
    "data_table_handwritten": (200, 0, 200),
    "photo": (220, 0, 0),
    "thumbprint": (220, 0, 0),
    "signature": (160, 32, 240),
    "stamp_seal": (255, 0, 128),
    "unknown": (128, 128, 128),
}


def draw_boxes(image_path: Path, detections, out_path: Path) -> None:
    img = Image.open(image_path).convert("RGB")
    scale = min(1.0, 1600 / max(img.size))      # review copy, not archival
    if scale < 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)),
                         Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    for d in detections:
        x1, y1, x2, y2 = d.box_norm
        x1, x2 = x1 * img.width, x2 * img.width
        y1, y2 = y1 * img.height, y2 * img.height
        color = COLORS.get(d.region_class, COLORS["unknown"])
        draw.rectangle([x1, y1, x2, y2], outline=color, width=4)
        label = d.region_class + (f": {d.content_hint[:25]}"
                                  if d.content_hint else "")
        draw.text((x1 + 4, max(0, y1 - 16)), label, fill=color)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)