"""Tests for the PDF merge step (configs/pdf_sources.yaml -> one source PDF)."""
import hashlib
from types import SimpleNamespace

import pymupdf as fitz
import pytest

from src.pdf_merge.merge import merge_pdfs
from src.pdf_merge.run_merge import merge_configured_pdfs, resolve_configured_pdfs
from src.utils.config_loader import config


def _make_pdf(path, text: str) -> None:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.save(str(path))
    doc.close()


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stub_pdfs(names: list[str]):
    return SimpleNamespace(pdfs=list(names))


def test_yaml_config_loads():
    """The config loader validates configs/pdf_sources.yaml (fail-fast)."""
    assert config.pdf_sources.pdfs
    assert all(isinstance(name, str) and name for name in config.pdf_sources.pdfs)


def test_resolve_multiple_pdfs_in_yaml_order(tmp_path, monkeypatch):
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        _make_pdf(tmp_path / name, name)
    monkeypatch.setattr(config, "pdf_sources", _stub_pdfs(["c.pdf", "a.pdf", "b.pdf"]))
    paths = resolve_configured_pdfs(raw_dir=tmp_path)
    assert [p.name for p in paths] == ["c.pdf", "a.pdf", "b.pdf"]


def test_missing_pdf_produces_clear_error(tmp_path, monkeypatch):
    _make_pdf(tmp_path / "a.pdf", "a")
    monkeypatch.setattr(config, "pdf_sources", _stub_pdfs(["a.pdf", "ghost.pdf"]))
    with pytest.raises(FileNotFoundError, match="ghost.pdf"):
        resolve_configured_pdfs(raw_dir=tmp_path)


def test_merge_preserves_yaml_order_and_output_exists(tmp_path, monkeypatch):
    for name, text in (("a.pdf", "PAGE_A"), ("b.pdf", "PAGE_B"), ("c.pdf", "PAGE_C")):
        _make_pdf(tmp_path / name, text)
    monkeypatch.setattr(config, "pdf_sources", _stub_pdfs(["c.pdf", "a.pdf", "b.pdf"]))
    out = merge_configured_pdfs(output_path=tmp_path / "merged.pdf", raw_dir=tmp_path)

    assert out.is_file() and out.stat().st_size > 0
    with fitz.open(str(out)) as merged:
        assert merged.page_count == 3
        texts = [merged[i].get_text().strip() for i in range(merged.page_count)]
    assert texts == ["PAGE_C", "PAGE_A", "PAGE_B"]


def test_original_pdfs_unchanged(tmp_path, monkeypatch):
    for name in ("a.pdf", "b.pdf"):
        _make_pdf(tmp_path / name, name)
    monkeypatch.setattr(config, "pdf_sources", _stub_pdfs(["a.pdf", "b.pdf"]))
    before = {p.name: _sha(p) for p in (tmp_path / "a.pdf", tmp_path / "b.pdf")}

    out = merge_configured_pdfs(output_path=tmp_path / "merged.pdf", raw_dir=tmp_path)

    assert out.is_file()
    after = {p.name: _sha(p) for p in (tmp_path / "a.pdf", tmp_path / "b.pdf")}
    assert before == after


def test_single_pdf_copied_into_merged_dir_sha_stable(tmp_path, monkeypatch):
    """One configured PDF is copied byte-for-byte into the merged folder —
    the pipeline always consumes data/merged/merged_source.pdf, and the
    copy keeps the file SHA (hence every document_id) stable: no
    re-encoding."""
    src = tmp_path / "solo.pdf"
    _make_pdf(src, "SOLO")
    monkeypatch.setattr(config, "pdf_sources", _stub_pdfs(["solo.pdf"]))
    merged_dir = tmp_path / "merged_out"
    before = _sha(src)

    out = merge_configured_pdfs(raw_dir=tmp_path, merged_dir=merged_dir)

    assert out == merged_dir / "merged_source.pdf"
    assert out.is_file()
    assert _sha(out) == before          # byte-identical -> document_ids stable
    assert _sha(src) == before          # original untouched


def test_single_pdf_copy_is_idempotent(tmp_path, monkeypatch):
    """Re-running the merge with unchanged input does not rewrite the file."""
    src = tmp_path / "solo.pdf"
    _make_pdf(src, "SOLO")
    monkeypatch.setattr(config, "pdf_sources", _stub_pdfs(["solo.pdf"]))
    merged_dir = tmp_path / "merged_out"

    first = merge_configured_pdfs(raw_dir=tmp_path, merged_dir=merged_dir)
    mtime = first.stat().st_mtime_ns
    second = merge_configured_pdfs(raw_dir=tmp_path, merged_dir=merged_dir)

    assert second == first
    assert first.stat().st_mtime_ns == mtime   # rewrite skipped


def test_merge_rejects_empty_input_list(tmp_path):
    with pytest.raises(ValueError):
        merge_pdfs([], tmp_path / "merged.pdf")


def test_default_output_goes_to_separate_merged_dir(tmp_path, monkeypatch):
    """The merged file must NOT land in the raw inputs folder — otherwise a
    later run could merge the merge again (recursive re-merging)."""
    for name in ("a.pdf", "b.pdf"):
        _make_pdf(tmp_path / name, name)
    monkeypatch.setattr(config, "pdf_sources", _stub_pdfs(["a.pdf", "b.pdf"]))
    merged_dir = tmp_path / "merged_out"

    out = merge_configured_pdfs(raw_dir=tmp_path, merged_dir=merged_dir)

    assert out.parent == merged_dir
    assert out.name == "merged_source.pdf"
    assert not (tmp_path / "merged_source.pdf").exists()
