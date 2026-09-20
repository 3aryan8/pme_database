"""Pydantic models for all data contracts.

Invalid config or data = pipeline halts at load/insert time.
This is the enforcement layer behind docs/group1_contract.md.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------- region config

class RegionClassConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typo'd YAML key = hard error
    extraction_classes: List[str]
    discard_classes: List[str]

    @field_validator("extraction_classes", "discard_classes")
    @classmethod
    def non_empty(cls, v: List[str]) -> List[str]:
        if not v or any(not s.strip() for s in v):
            raise ValueError("class lists must be non-empty, non-blank strings")
        return v

# ---------------------------------------------------------------- field schema
# v2 (2026-09-08): hierarchical, page-structured schema.
# - The tree mirrors the physical report: top-level section per page,
#   nested objects for printed boxes/tables, arrays for row-wise tables.
# - Leaves (string/integer/float/date/boolean) are the only scoreable units;
#   containers carry structure, hints and the page the section belongs to.
# - `page` (1-based, document-relative) lets the runner ask each page only
#   for the fields that can appear on it.

class FieldDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_name: str = Field(min_length=1)
    data_type: Literal["string", "integer", "float", "date", "boolean",
                       "object", "array"]
    source_type: Optional[Literal["typed", "handwritten"]] = None
    printed_row_label: Optional[str] = None
    extraction_hint: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1)   # section -> doc page
    children: Optional[List["FieldDefinition"]] = None   # data_type: object
    item: Optional["FieldDefinition"] = None             # data_type: array
    template_rows: Optional[List[Dict[str, Any]]] = None  # GT scaffolding (arrays)

    @model_validator(mode="after")
    def _check_shape(self) -> "FieldDefinition":
        if self.data_type == "object" and not self.children:
            raise ValueError(
                f"object field '{self.field_name}' needs non-empty children")
        if self.data_type == "array" and self.item is None:
            raise ValueError(
                f"array field '{self.field_name}' needs an item schema")
        if self.children is not None and self.data_type != "object":
            raise ValueError(
                f"'{self.field_name}': children only allowed on object fields")
        if self.item is not None and self.data_type != "array":
            raise ValueError(
                f"'{self.field_name}': item only allowed on array fields")
        if self.data_type not in ("object", "array") and self.source_type is None:
            raise ValueError(
                f"leaf field '{self.field_name}' needs source_type")
        return self


FieldDefinition.model_rebuild()


class SchemaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: List[FieldDefinition] = Field(min_length=1)

# ---------------------------------------------------------------- manifest rows

class AssemblyRow(BaseModel):
    """Phase 3 output. One row = one page of one person-document."""
    model_config = ConfigDict(extra="forbid")
    document_id: str                      # person_document_id (see id_generator)
    page_index: int = Field(ge=0)         # page within the person-document
    source_page_number: int = Field(ge=1) # 1-based page in the SOURCE pdf
    person_index: int = Field(ge=0)       # person within the source pdf
    source_file_sha256: str               # sha256 of the source pdf
    high_res_raw_path: str                # RELATIVE to project root (portable)
    file_mtime: str
    raw_page_width_pts: float
    effective_dpi_estimate: float = Field(ge=0)
    render_dpi_used: float = Field(ge=0)  # actual raw-render DPI (adaptive: min(source, cap))
    low_source_quality_flag: bool
    split_check_status: Literal[
        "manually_cleared", "flagged", "deferred_to_phase7", "pending_inspection"
    ]

    @field_validator("document_id", "source_file_sha256")
    @classmethod
    def check_sha256(cls, v: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", v):
            raise ValueError("must be a 64-char lowercase sha256 hex")
        return v

    @field_validator("file_mtime")
    @classmethod
    def iso_datetime(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("file_mtime must be ISO-8601")
        return v
    

class ManifestRow(AssemblyRow):
    """Final manifest row after Phase 4 (cleaned + VLM copies exist)."""
    high_res_path: str      # CLEANED image (consumption path, dims free)
    vlm_res_path: str
    vlm_res_width: int
    blank_page_flag: bool = False   # near-blank page (e.g. duplex backsides)


# ---------------------------------------------------------------- extraction

class ProvenanceEntry(BaseModel):
    """Where a value came from. Baseline: page-level. Phase 7 adds region."""
    model_config = ConfigDict(extra="forbid")
    page_index: int = Field(ge=0)
    model: str
    extracted_at: str
    raw_value: str = ""


class ExtractionRecord(BaseModel):
    """Document-level merged extraction (the Group 2 output contract).
    v2: `fields` is NESTED — mirrors the schema tree; leaves are str|null."""
    model_config = ConfigDict(extra="forbid")
    document_id: str
    model: str
    fields: Dict[str, Any]
    provenance: Dict[str, ProvenanceEntry] = Field(default_factory=dict)
    conflicts: List[str] = Field(default_factory=list)  # fields with >1 value across pages
    pages_covered: List[int] = Field(default_factory=list)


class GroundTruthDoc(BaseModel):
    """Hand-typed ground truth, one file per person-document.
    null = field genuinely absent/empty on the form.
    '?'  = present but unreadable to the annotator (excluded from scoring).
    """
    model_config = ConfigDict(extra="forbid")
    document_id: str
    annotator: str
    fields: Dict[str, Any]    # v2: nested, mirrors the schema tree
    notes: Optional[str] = None