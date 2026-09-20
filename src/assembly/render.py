"""Renders source PDF pages to adaptive-DPI PNGs + estimates scan quality.

Adaptive rendering rule (replaces the old fixed-300-DPI behavior):

    page_dpi = min(effective_source_dpi, render_dpi cap)

- Scans below the cap render at NATIVE resolution — never upscaled.
  Upscaled pixels carry no information; they only inflate image size,
  OCR workload, and VLM token cost.
- Scans above the cap render at the cap (no wasted pixels).
- Digital-native pages (no dominant raster) render at the cap — vector
  content is always rasterized at full quality.

Pages whose effective DPI falls below `low_source_dpi_threshold` are
flagged (`low_source_quality_flag`) so downstream stages can handle them.
"""
import pymupdf as fitz

from src.utils.config_loader import config

# A page counts as a "scan" only if its dominant embedded raster covers at
# least this fraction of the page area. Smaller images (logos, embedded
# photos inside a vector page) must NOT pull the render DPI down.
SCAN_COVERAGE_MIN = 0.5


def _cap() -> float:
    return float(config.pipeline.rendering.render_dpi)


def effective_dpi(pdf: fitz.Document, page: fitz.Page) -> float:
    """Estimate the source resolution of one page.

    Scanned pages: pixels-per-inch of the dominant (largest displayed
    area) embedded raster. Digital-native pages — no raster covering
    >= 50% of the page — return the render-DPI cap, so they are never
    flagged low and always render at the cap.
    """
    rect = page.rect
    page_area = rect.width * rect.height
    best_eff, best_cover = 0.0, 0.0
    for img in page.get_images(full=True):
        xref = img[0]
        try:
            info = pdf.extract_image(xref)
            px = max(info["width"], info["height"])
        except Exception:
            continue
        try:
            irects = page.get_image_rects(xref)
        except Exception:
            irects = [rect]
        if not irects:
            irects = [rect]
        for ir in irects:
            if ir.width <= 0 or ir.height <= 0 or page_area <= 0:
                continue
            cover = (ir.width * ir.height) / page_area
            disp_in = max(ir.width, ir.height) / 72.0
            eff = px / disp_in
            if cover > best_cover:
                best_cover, best_eff = cover, eff
    if best_eff == 0 or best_cover < SCAN_COVERAGE_MIN:
        return _cap()
    return best_eff


def render_dpi_for_page(pdf: fitz.Document, page: fitz.Page) -> float:
    """DPI to render this page: min(effective source DPI, configured cap)."""
    return round(min(effective_dpi(pdf, page), _cap()), 1)


def render_person_pages(pdf: fitz.Document, first: int, last: int, out_dir) -> list:
    """Render 1-based inclusive range. Returns per-page records.

    Each page renders at its own adaptive DPI (see module docstring);
    records carry the effective estimate, the DPI actually used, and the
    low-source-quality flag so the manifest needs no re-estimation.
    """
    threshold = config.pipeline.quality_checks["low_source_dpi_threshold"]
    records = []
    for page_index, source_page_number in enumerate(range(first, last + 1)):
        page = pdf[source_page_number - 1]
        est = effective_dpi(pdf, page)
        dpi = min(est, _cap())
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        out_path = out_dir / f"page_{page_index:04d}.png"
        pix.save(out_path)
        records.append({
            "page_index": page_index,
            "source_page_number": source_page_number,
            "path": out_path,
            "effective_dpi_estimate": round(est, 1),
            "render_dpi_used": round(dpi, 1),
            "low_source_quality_flag": est < threshold,
        })
    return records
