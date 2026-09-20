"""Adaptive rendering tests (synthetic PDFs — no real data needed).

Rule under test: page dpi = min(effective source dpi, render_dpi cap).
- digital-native page      -> renders at the cap (300)
- vector page w/ a logo    -> STILL renders at the cap (logo must not shrink it)
- 120 DPI full-page scan   -> renders at 120 (NOT upscaled to 300), flagged low
- 600 DPI full-page scan   -> capped at 300 (no wasted pixels)
"""
import io

import pymupdf as fitz
import pytest
from PIL import Image, ImageDraw

from src.assembly.render import effective_dpi, render_dpi_for_page, render_person_pages
from src.utils.config_loader import config

W, H = 612, 792  # US Letter, points
CAP = float(config.pipeline.rendering.render_dpi)


def _scan_stream(dpi: int) -> bytes:
    """Full-page white 'scan' raster at the given native DPI."""
    img = Image.new("RGB", (int(W / 72 * dpi), int(H / 72 * dpi)), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, img.width - 1, img.height - 1], outline="black", width=2)
    d.text((img.width // 4, img.height // 4), "scan", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def pdf(tmp_path):
    doc = fitz.open()

    # page 0: digital-native (text only)
    p0 = doc.new_page(width=W, height=H)
    p0.insert_text((72, 100), "Digital native page")

    # page 1: vector page with a small embedded logo image
    p1 = doc.new_page(width=W, height=H)
    p1.insert_text((72, 100), "Vector page with logo")
    logo = Image.new("RGB", (120, 120), "white")
    ImageDraw.Draw(logo).text((10, 50), "L", fill="black")
    lbuf = io.BytesIO()
    logo.save(lbuf, format="PNG")
    p1.insert_image(fitz.Rect(500, 50, 620, 170), stream=lbuf.getvalue())

    # pages 2-3: full-page scans at 120 DPI and 600 DPI
    for dpi in (120, 600):
        p = doc.new_page(width=W, height=H)
        p.insert_image(p.rect, stream=_scan_stream(dpi))

    path = tmp_path / "synthetic.pdf"
    doc.save(str(path))
    doc.close()
    return fitz.open(str(path))


def test_digital_page_renders_at_cap(pdf):
    assert effective_dpi(pdf, pdf[0]) == pytest.approx(CAP)
    assert render_dpi_for_page(pdf, pdf[0]) == CAP


def test_vector_page_with_logo_renders_at_cap(pdf):
    # The 120px logo covers ~3% of the page — it must not count as a scan.
    assert render_dpi_for_page(pdf, pdf[1]) == CAP


def test_low_scan_estimated_and_not_upscaled(pdf):
    est = effective_dpi(pdf, pdf[2])
    assert est == pytest.approx(120, rel=0.05)
    assert render_dpi_for_page(pdf, pdf[2]) == pytest.approx(120, rel=0.05)


def test_high_scan_capped(pdf):
    est = effective_dpi(pdf, pdf[3])
    assert est >= CAP
    assert render_dpi_for_page(pdf, pdf[3]) == CAP


def test_render_pixel_math_and_flags(pdf, tmp_path):
    recs = render_person_pages(pdf, 1, 4, tmp_path)
    assert len(recs) == 4
    for rec in recs:
        with Image.open(rec["path"]) as img:
            expected_w = (W / 72) * rec["render_dpi_used"]
            assert abs(img.width - expected_w) <= 2, (
                f"page {rec['page_index']}: {img.width}px != ~{expected_w:.0f}px "
                f"@ {rec['render_dpi_used']} DPI")
    # digital at cap
    assert recs[0]["render_dpi_used"] == CAP
    assert recs[0]["low_source_quality_flag"] is False
    # logo page at cap (not shrunken to the logo's DPI)
    assert recs[1]["render_dpi_used"] == CAP
    # 120 DPI scan rendered at native 120 — never upscaled — and flagged
    assert recs[2]["render_dpi_used"] == pytest.approx(120, rel=0.05)
    assert recs[2]["low_source_quality_flag"] is True
    # 600 DPI scan capped at 300
    assert recs[3]["render_dpi_used"] == CAP
    assert recs[3]["low_source_quality_flag"] is False


def test_manifest_row_accepts_render_dpi_used():
    from src.models.schemas import AssemblyRow
    row = AssemblyRow(
        document_id="a" * 64,
        page_index=0,
        source_page_number=1,
        person_index=0,
        source_file_sha256="b" * 64,
        high_res_raw_path="data/interim/high_res/x/page_0000.png",
        file_mtime="2026-01-01T00:00:00+00:00",
        raw_page_width_pts=612.0,
        effective_dpi_estimate=120.0,
        render_dpi_used=120.0,
        low_source_quality_flag=True,
        split_check_status="manually_cleared",
    )
    assert row.render_dpi_used == 120.0


def test_manifest_row_requires_render_dpi_used():
    from pydantic import ValidationError
    from src.models.schemas import AssemblyRow
    with pytest.raises(ValidationError):
        AssemblyRow(
            document_id="a" * 64,
            page_index=0,
            source_page_number=1,
            person_index=0,
            source_file_sha256="b" * 64,
            high_res_raw_path="data/interim/high_res/x/page_0000.png",
            file_mtime="2026-01-01T00:00:00+00:00",
            raw_page_width_pts=612.0,
            effective_dpi_estimate=120.0,
            # render_dpi_used intentionally missing
            low_source_quality_flag=True,
            split_check_status="manually_cleared",
        )
